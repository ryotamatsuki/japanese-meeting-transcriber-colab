"""Download one short CC BY 4.0 Japanese two-speaker validation recording.

Only the downloader is versioned. Audio/provenance stay in ignored local_audio/.
The historic dialect recording is a functional smoke test, not a meeting-ASR
accuracy benchmark. Never infer speaker accuracy from the known count alone.
"""
import hashlib
import json
from pathlib import Path
import urllib.request

URL = 'https://upload.wikimedia.org/wikipedia/commons/e/e6/Kyoto_women_conversation_in_1964.ogg'
SHA256 = '9f6a382ddeffc9e74d9a94954b66c6ed43ae3a3ae1d2fede03747845c2e10124'


def main():
    output = Path('local_audio')
    output.mkdir(exist_ok=True)
    request = urllib.request.Request(URL, headers={'User-Agent': 'MeetingTranscriberStage1/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        audio = response.read(2 * 1024 * 1024)
    if hashlib.sha256(audio).hexdigest() != SHA256:
        raise ValueError('Unexpected validation audio SHA256; do not run inference')
    (output / 'kyoto_two_speakers.ogg').write_bytes(audio)
    provenance = {
        'title': 'Kyoto women conversation in 1964',
        'source': 'https://commons.wikimedia.org/wiki/File:Kyoto_women_conversation_in_1964.ogg',
        'original_source': 'https://mmsrv.ninjal.ac.jp/hogenrokuon_siryo/',
        'credit': '国立国語研究所（上村幸雄、徳川宗賢）・方言録音資料シリーズ11「京都市方言」',
        'license': 'https://creativecommons.org/licenses/by/4.0/',
        'license_basis': 'Original source licenses series 3-15 audio under CC BY 4.0.',
        'download_url': URL, 'sha256': SHA256, 'bytes': len(audio),
        'documented_speakers': 2, 'changes': 'None; downloaded Ogg excerpt as published.',
        'reference_subtitles': 'https://commons.wikimedia.org/wiki/TimedText:Kyoto_women_conversation_in_1964.ogg.ja.srt',
        'limitations': 'Historic Kyoto dialect; subtitle intervals are not verified speaker reference intervals.',
    }
    (output / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Verified short CC BY 4.0 test audio; audio and provenance are in ignored local_audio/.')


if __name__ == '__main__':
    main()
