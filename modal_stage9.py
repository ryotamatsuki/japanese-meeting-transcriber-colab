"""Stage9: research-only A10 overlap separation vs independent-tracks oracle.

The isolated function uses a publicly licensed Japanese 2-speaker sample,
SpeechBrain's English WSJ0-2Mix SepFormer on 8k mono WAV, and identical
faster-whisper large-v3 decoding for three paired conditions:
  mixed audio -> single ASR text (two-speaker cpCER penalty);
  separated estimated channels -> ASR each;
  actual individual channels -> ASR each (unavailable at inference, upper bound).

Never copies oracle channels into production inference. No web endpoints.
The CLI only writes aggregated metrics, not raw audio or transcription text.
"""
from pathlib import Path
import modal

app=modal.App('japanese-meeting-transcriber-stage9-research')
weights=modal.Volume.from_name('meeting-transcriber-models-v1',create_if_missing=True)
image=(modal.Image.debian_slim(python_version='3.11')
       .apt_install('ffmpeg','libsndfile1')
       .pip_install_from_requirements('requirements-modal.lock',
                                     extra_index_url='https://download.pytorch.org/whl/cu128')
       .pip_install('speechbrain==1.0.3','rapidfuzz==3.14.3')
       .run_commands(
           "python -c \"import pathlib,site;p=pathlib.Path(site.getsitepackages()[0])/'nvidia';"
           "pathlib.Path('/etc/ld.so.conf.d/99-transcriber.conf').write_text('\\n'.join(str(d) for d in p.glob('*/lib')))\"",
           'ldconfig','python -m pip check')
       .env({'HF_HOME':'/models/hf','HF_HUB_CACHE':'/models/hf/hub','HF_HUB_DISABLE_TELEMETRY':'1'})
       .add_local_python_source('scripts','beta'))


@app.function(image=image,gpu='A10',cpu=2,memory=8192,timeout=960,
              max_containers=1,scaledown_window=2,
              volumes={'/models':weights},single_use_containers=True)
def analyze_overlap_clip(mixed_wav:bytes,track1_wav:bytes,track2_wav:bytes,
                         text1:str,text2:str,clip_label:str):
    import io,math,os,time,tempfile
    import numpy as np
    import soundfile as sf
    import torch
    from scipy.signal import resample_poly
    from speechbrain.inference.separation import SepformerSeparation
    from faster_whisper import WhisperModel
    from scripts.evaluate_attributed_transcript import permutation_cer
    from scripts.evaluate_asr_cer import normalized_ja

    def load(raw):
        if len(raw)>400000 or not raw:
            raise ValueError('Research clip too large')
        data,sr=sf.read(io.BytesIO(raw),dtype='float32',always_2d=False)
        if sr!=8000 or data.ndim!=1 or len(data)>8000*8 or len(data)<8000:
            raise ValueError('Research clips must be 1-8s mono PCM 8kHz')
        return np.asarray(data,dtype=np.float32)

    mixed,one,two=load(mixed_wav),load(track1_wav),load(track2_wav)
    size=min(len(mixed),len(one),len(two))
    if not (8000<=size<=64000):raise ValueError('Invalid clip length')
    mixed,one,two=mixed[:size],one[:size],two[:size]
    if not text1.strip() or not text2.strip():raise ValueError('Human reference speaker transcript missing')
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')

    with tempfile.TemporaryDirectory(prefix='stage9-sandbox-') as tmp:
        root=Path(tmp)
        sf.write(root/'mix8.wav',mixed,8000,subtype='PCM_16')
        begun=time.perf_counter()
        separator=SepformerSeparation.from_hparams(
            source='speechbrain/sepformer-wsj02mix',
            savedir=str(root/'sepformer'),run_opts={'device':'cuda'})
        estimates=separator.separate_file(path=str(root/'mix8.wav'))
        sep_seconds=time.perf_counter()-begun
        if estimates.ndim!=3 or estimates.shape[-1]!=2:
            raise ValueError('Separation output shape not two sources')
        estimated=estimates.detach().cpu().numpy()[0,:,:]
        del separator,estimates
        torch.cuda.empty_cache()
        if estimated.shape[0]!=size:
            estimated=np.stack([np.interp(np.linspace(0,1,size),
                     np.linspace(0,1,estimated.shape[0]),estimated[:,i]) for i in range(2)],axis=-1)
        model=WhisperModel('large-v3',device='cuda',compute_type='float16',
                           download_root='/models/whisper')
        def infer(samples,name):
            samples=np.asarray(samples,dtype=np.float32)
            if not np.all(np.isfinite(samples)):raise ValueError('Nonfinite separated speech')
            samples=resample_poly(samples,2,1).astype('float32')
            peak=max(float(np.max(np.abs(samples))),1e-5)
            if peak>0.99:samples=samples*(0.99/peak)
            path=root/(name+'.wav')
            sf.write(path,samples,16000,subtype='PCM_16')
            segments,_=model.transcribe(str(path),language='ja',task='transcribe',
                beam_size=5,condition_on_previous_text=False,
                vad_filter=False,word_timestamps=False)
            return ''.join(s.text for s in segments)
        begin_asr=time.perf_counter()
        outputs={'mixture':[infer(mixed,'mixture')],
                 'sepformer':[infer(estimated[:,0],'estimated1'),
                               infer(estimated[:,1],'estimated2')],
                 'oracle_individual_tracks':[infer(one,'oracle1'),infer(two,'oracle2')]}
        asr_seconds=time.perf_counter()-begin_asr
        reference=[{'start':0,'end':size/8000,'speaker_id':f'speaker_{i}',
                    'text':value} for i,value in enumerate((text1,text2),start=1)]
        scores={}
        for mode,parts in outputs.items():
            hyp=[{'start':0,'end':size/8000,'speaker':f'prediction_{i}',
                  'text':p} for i,p in enumerate(parts,start=1)]
            out=permutation_cer(reference,hyp)
            scores[mode]={'cpcer':out['cpcer'],
                          'normalized_hypothesis_characters':out['hypothesis_characters'],
                          'reference_characters':out['reference_characters'],
                          'edit_distance':out['edit_distance']}
        def si_snr(pred,ref):
            x=np.asarray(pred,dtype=np.float64)
            r=np.asarray(ref,dtype=np.float64)
            x=x-x.mean();r=r-r.mean()
            if float(np.dot(r,r))<1e-10:
                return None
            target=(np.dot(x,r)/(np.dot(r,r)+1e-12))*r
            noise=x-target
            return 10*math.log10((np.dot(target,target)+1e-10)/(np.dot(noise,noise)+1e-10))
        sep_si=[]
        refs=(one,two)
        for perm in ((0,1),(1,0)):
            baselines=[si_snr(mixed,refs[i]) for i in range(2)]
            outputs_si=[si_snr(estimated[:,perm[i]],refs[i]) for i in range(2)]
            if any(z is None for z in baselines+outputs_si):
                continue
            sep_si.append(sum(outputs_si)/2-sum(baselines)/2)
        weights.commit()
        return {'label':clip_label,'duration_seconds':size/8000,
                'mode_results':scores,
                'separation_seconds':sep_seconds,'five_asr_streams_seconds':asr_seconds,
                'best_pair_sisnri_db':max(sep_si) if sep_si else None,
                'model':'speechbrain/sepformer-wsj02mix (WSJ English clean 8k)',
                'asr':'faster-whisper large-v3 Japanese',
                'oracle_condition':'real separate mic tracks; not available from ordinary single-channel recording',
                'reference_license':'IngCrowd CC BY-NC 4.0, noncommercial study only',
                'warning':'Human-ELAN oracle selected clip, English 8k source separator, mix may not equal the sum of Zoom individual tracks; not an operational performance estimate'}


@app.local_entrypoint()
def main(mixed:str,sp1:str,sp2:str,reference_file:str,output:str='local_runs/stage9.json'):
    import json
    from pathlib import Path
    ref=json.loads(Path(reference_file).read_text(encoding='utf-8'))
    r=analyze_overlap_clip.remote(Path(mixed).read_bytes(),
         Path(sp1).read_bytes(),Path(sp2).read_bytes(),
         ref['speaker_text']['speaker_1'],ref['speaker_text']['speaker_2'],ref['label'])
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    # Expose no audio or transcript to CI output.
    print('STAGE9_NUMERIC_METRICS_ONLY',json.dumps(
        {'label':r['label'],'cpcer':{k:v['cpcer'] for k,v in r['mode_results'].items()},
         'separation_seconds':r['separation_seconds'],
         'si_snri_db':r['best_pair_sisnri_db']}))
