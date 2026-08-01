# Resort tower hydronic telemetry

Run `./generate_resort_hydronic.py` to reproduce the two CSV fixtures with the
fixed seed declared in the generator. The generator produces telemetry only;
the CSVs are uploaded to the normal historical assessment UI and are evaluated
by Neraium's production assessment service.

`hidden-event.json` is intentionally separate from both CSVs and from the
frontend's served files. The browser test does not read it until the blinded
analysis response is complete and locked.
