# The human-designer study and the live demo

The web app of the study with human designers in the paper (Q4 and Appendix B), now the live demo at https://cert3nf.onrender.com.
On the demo, *Try it* opens a session of your own on one of the study's three tables, or on a CSV that you upload, and ends with the design that your answers certify.
The study has ended, so the site no longer accepts participants.

## Layout

| path | content |
|---|---|
| `code/` | the web server (`server.py`), its pages, one session of questions (`session.py`), uploaded tables (`upload.py`) and the tests |
| `blocks/` | the fixed block of questions about each relation |
| `prebuilt/` | each relation, its data and its advisor, built by `code/build_kit.py` |
| `docs/` | the documentation of the relations |
| `materials/` | the instructions, the exit questionnaire and the debrief |

## Running it

```bash
python study/code/server.py                   # the site at http://127.0.0.1:8765
python study/code/test_session.py             # sessions: answer modes, replay, resume, several at once
python study/code/test_upload.py              # uploads and several visitors at once
```
