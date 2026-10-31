# Candidate Japanese meeting corpora and permission gates (2026-10-31)

This note records acquisition diligence, **not completed retrieval**. Never feed a dataset into a cloud GPU merely because it is downloadable.

| Candidate | Technical fit | Access / rights verified | v1 suitability now |
|---|---|---|---|
| [RWCP-SP01 (NII IDR)](https://www.nii.ac.jp/dsc/idr/speech/submit/RWCP-SP01.html) | Seven enacted Japanese 4–5 speaker meetings, mixed/individual microphones, synchronized records; promising for multi-speaker attribution diagnostics | Research-only, free of charge but requires application. Web listing updated 2026-03-16. Specific annotations and cloud transfer permission must be checked after grant. | **Not acquired**. Historical staged discussions, not current real administrative meetings. |
| [Qlean Japanese business meetings](https://qleandataset.visual-bank.co.jp/datasets/speech-meetings) | 2/3-speaker natural business-theme recordings with transcripts | Sample by request; licensing and upload/Modal use by separate terms | **Not acquired**. Commercial quality test candidate after contract and audio-reference inspection. |
| [J-CRe3](https://github.com/riken-grp/J-CRe3) | Human turn transcripts; two actors in domestic activity dialogue | CC BY-SA 4.0 used by PR #6 pilot; three source recordings already tuned | **Development only**, not unseen real meeting. |
| [IngCrowd Japanese themed dialogue](https://www.ingcrowd.jp/datasets/) | 2-speaker dialogs and annotated turns | Original experiments used 10 recordings under noncommercial evaluation conditions | **Development only**, no new holdout claim. |
| [BTSJ Japanese natural conversation](https://mmsrv.ninjal.ac.jp/btsj/) | Many real Japanese conversations and some audio/transcripts | Education/research only; terms expressly prohibit internet upload/public transmission. | **Do not upload to Modal** without written authorization. No v1 cloud data source. |
| [ReazonSpeech](https://huggingface.co/datasets/reazon-research/reazonspeech) | Japanese broadcast speech with paired text; helpful single-stream ASR research | Explicit Japanese Copyright Act Article 30-4 use restriction | **Not** a substitute for real meetings or permission-free hosted commercial product benchmarking. |

## Required compliance ledger for every future evaluation source

Source revision, individual recording IDs, reference and audio SHA256, evidence of participant consent / redistribution / cloud-processor transfer, term dates, speech use scope (research vs commercial), number of original independent meetings, acoustic channel details, human annotation rules, provenance, known overlap and list of reviewers. Preserve this ledger outside public PRs if it contains identifiable detail. A request or a webpage listing is not the permission grant.

No sample request, purchase, license agreement or GPU inference on these candidates was performed in this research PR.

The first executable v1 gate is **a permission-cleared collection of genuinely independent real meetings with human transcript references**. Not all recordings within a single session count independently. Only after an explicit grant and materialization of approved files can frozen-stage ablations produce a valid new empirical result.
