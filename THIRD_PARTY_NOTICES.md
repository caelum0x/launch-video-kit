# Third-party notices

The skills, scripts, template and documents in this repository are MIT licensed (see [LICENSE](LICENSE)). They call, but do not include, these tools:

| Tool | Used for | Licence |
|---|---|---|
| [HyperFrames](https://github.com/heygen-com/hyperframes) (`npx hyperframes@0.8.77`) | rendering the film from HTML | Apache-2.0 |
| [GSAP](https://gsap.com) (loaded from jsDelivr at render time) | the timeline the film seeks | GSAP standard licence, free for commercial use |
| [Puppeteer](https://pptr.dev) | the website to brand extractor | Apache-2.0 |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | checking and timing spoken words | MIT |
| [torchaudio](https://pytorch.org/audio) MMS forced aligner | precise word timing | BSD-2-Clause; the MMS model weights are published under CC-BY-NC 4.0, so check that your use fits, or align with whisper instead (`prep_lines.py --align whisper`) |
| [pedalboard](https://github.com/spotify/pedalboard), librosa, numpy, scipy, soundfile, pyloudnorm | audio processing and mixing | GPL-3.0 (pedalboard), ISC, BSD, BSD, BSD, MIT |
| [Chatterbox](https://github.com/resemble-ai/chatterbox), [ACE-Step](https://github.com/ace-step/ACE-Step) | optional local voice clone and music | MIT, Apache-2.0 |
| [Higgsfield](https://higgsfield.ai) CLI | optional paid voice, music, sound kits and footage on your own account | provider terms |

The Acme example (`examples/acme-site/`, `brand/`, `film/assets/screens/`) is a fictional brand made for this repository. Its font, Plus Jakarta Sans, is distributed under the SIL Open Font License ([OFL.txt](examples/acme-site/fonts/OFL.txt)); the extracted copy in `brand/fonts/` carries the same licence. Product names and logos mentioned in the documents (Apple, Lovable and others) belong to their owners and are named only as style references.
