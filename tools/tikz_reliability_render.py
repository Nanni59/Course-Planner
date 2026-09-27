"""Opt-in real compiler check: python tools/tikz_reliability_render.py OUTPUT_DIR.

Requires the backend dependencies, pdflatex and pdftocairo. Uses no API calls.
Writes PNGs and a browser-test worksheet fixture only to the explicit output path.
"""
import base64
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
with patch.object(threading.Thread, 'start'):
    from hf_space_tikz import app

def no_model(*args, **kwargs):
    raise AssertionError('Unexpected model call in deterministic render test')

def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app._gemini = no_model
    print('Local Gemini configured:', bool(app.GEMINI_KEYS))
    fixtures = json.loads((ROOT / 'tools/fixtures/worksheet_reliability.json').read_text(encoding='utf-8'))
    variations = [
        'Triangle ABC is right-angled at A. AB = 7 cm and AC = 24 cm. Find BC. Draw AB vertically and AC horizontally. Label BC as x.',
        'Points P(-3,2) and Q(4,-2) lie on a coordinate plane. Find the midpoint of PQ. Show both axes from -5 to 5. Plot P(-3,2) and Q(4,-2). Do not mark the midpoint.',
        'Plot the quadratic y = 0.5x^2-2x-1 over -3 <= x <= 5. Show the y-axis from -5 to 10. Do not mark the vertex or intercepts.',
        'A circle has centre O and radius 5 cm. OP = 13 cm. PT is tangent to the circle at T. Find PT. Label OT = 5 cm and OP = 13 cm and PT = x.',
        'A block experiences four forces: 10 N upward, 10 N downward, 8 N to the right, 3 N to the left. Find the resultant force. Do not draw the resultant force.',
        'Points A, B, and C lie on the circumference of a circle with center O. If angle AOB = 80 degrees, what is the measure of angle ACB?',
    ]
    for batch, texts in [('exact',[q['question']+'\nDiagram: '+q['visualDescription'] for q in fixtures]), ('variation',variations)]:
        for number, text in enumerate(texts,1):
            req = app.GenerateReq(title=text,brief='Question: '+text,subject='',target='worksheet',theme='mono',format='png')
            job_id = f'{batch}-{number}'
            app.jobs[job_id] = {'status':'pending'}
            app._run_generate_job(job_id,req)
            result = app.status(job_id)
            assert result['status']=='completed', result
            assert result['source'].startswith('elementary:'), result
            assert not any(e['stage'].startswith('model-') for e in result['diagnostics'])
            (output / f'{job_id}.png').write_bytes(base64.b64decode(result['base64']))
            if batch == 'exact':
                fixtures[number-1]['tikzPng'] = result['base64']
                fixtures[number-1]['visualDiagnostic'] = {k:result[k] for k in ('status','source','diagnostics')}
            print(job_id,result['source'])
    (output / 'rendered-fixture.json').write_text(json.dumps(fixtures),encoding='utf-8')

if __name__ == '__main__':
    main()
