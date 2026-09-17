"""Compile the integration, statistics, and functions acceptance templates.

Run with the backend environment:
    python tools/tikz_subject_templates_render.py OUTPUT_DIR

No model calls are made. The supplied parameters mirror the broad-prompt
acceptance matrix in tools/fixtures/worksheet_subject_matrix.json.
"""
import base64
from pathlib import Path
import sys
import threading
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

with patch.object(threading.Thread, 'start'):
    from hf_space_tikz import app
    from hf_space_tikz import templates


CASES = [
    ('integration', 'definite_integral_shaded', {
        'CURVE':'x^2+1', 'XMIN':'-1', 'XMAX':'3', 'YMIN':'0', 'YMAX':'11',
        'A':'0', 'B':'2', 'A_LABEL':'$0$', 'B_LABEL':'$2$',
        'AREA_LABEL_X':'1', 'AREA_LABEL_Y':'2.2', 'AREA_LABEL':'area',
    }, 'Evaluate the definite integral of x^2 + 1 from x = 0 to x = 2.'),
    ('riemann', 'riemann_sum_rectangles', {
        'CURVE':'x+1', 'XMIN':'0', 'XMAX':'4.5', 'YMIN':'0', 'YMAX':'6',
        'X0':'0', 'X1':'1', 'X2':'2', 'X3':'3', 'X4':'4',
        'H1':'1', 'H2':'2', 'H3':'3', 'H4':'4',
    }, 'Use four left-endpoint rectangles to estimate the area under y = x + 1 on 0 <= x <= 4.'),
    ('histogram', 'histogram', {
        'YMAX':'10', 'L1':'0--9', 'L2':'10--19', 'L3':'20--29', 'L4':'30--39', 'L5':'40--49',
        'F1':'3', 'F2':'7', 'F3':'9', 'F4':'5', 'F5':'2',
    }, 'Describe a grouped distribution with five stated class intervals and frequencies.'),
    ('boxplot', 'boxplot', {
        'XMIN':'8', 'XMAX':'44', 'MIN':'12', 'Q1':'18', 'MED':'25', 'Q3':'31', 'MAX':'40',
    }, 'Draw a box plot for the five-number summary 12, 18, 25, 31, 40.'),
    ('scatter', 'scatter_fit', {
        'XMIN':'0', 'XMAX':'6', 'YMIN':'0', 'YMAX':'10', 'XLABEL':'study time', 'YLABEL':'quiz score',
        'X1':'1', 'Y1':'2', 'X2':'2', 'Y2':'3', 'X3':'3', 'Y3':'5',
        'X4':'4', 'Y4':'6', 'X5':'5', 'Y5':'8', 'M':'1.5', 'B':'0.2',
    }, 'Describe the correlation of five stated ordered pairs.'),
    ('normal', 'normal_curve', {
        'MU':'500', 'SIGMA':'4', 'SHADE_L':'496', 'SHADE_R':'504',
        'T1':'$492$', 'T2':'$496$', 'T3':'$500$', 'T4':'$504$', 'T5':'$508$',
    }, 'Represent the interval within one standard deviation of a normal distribution with mean 500 and standard deviation 4.'),
    ('ogive', 'ogive', {
        'XMIN':'0', 'XMAX':'55', 'YMAX':'35',
        'X1':'10', 'C1':'2', 'X2':'20', 'C2':'8', 'X3':'30', 'C3':'17',
        'X4':'40', 'C4':'24', 'X5':'50', 'C5':'30',
    }, 'Estimate the median from an ogive with five stated cumulative-frequency points.'),
    ('exponential', 'exponential_asymptote', {
        'A':'0.5', 'B':'2', 'K':'3', 'LABEL_K':'?',
    }, 'Describe the transformations and asymptote of y = 2^(x - 1) + 3.'),
    ('rational', 'rational_asymptotes', {
        'XMIN':'-5', 'XMAX':'7', 'YMIN':'-6', 'YMAX':'10',
        'A':'7', 'H':'3', 'K':'2', 'LABEL_H':'?', 'LABEL_K':'?',
    }, 'Identify the vertical and horizontal asymptotes of f(x) = (2x + 1)/(x - 3).'),
    ('sinusoid', 'sinusoid_amplitude_period', {
        'AMPLITUDE_VALUE':'3', 'MIDLINE_VALUE':'-2',
        'AMPLITUDE_LABEL':'$A$', 'MIDLINE_LABEL':'midline', 'PERIOD_LABEL':'$P$',
    }, 'Determine the amplitude, period, and midline of y = 3 sin(x) - 2.'),
    ('piecewise', 'piecewise_linear', {
        'M1':'1', 'B1':'2', 'M2':'-1', 'B2':'5', 'C':'1', 'LABEL_BREAK':'$x=1$',
    }, 'Graph f(x) = x + 2 for x < 1 and f(x) = 5 - x for x >= 1.'),
    ('inverse', 'function_inverse_reflection', {
        'BASE':'2', 'F_LABEL':'$f$', 'INV_LABEL':'$f^{-1}$',
    }, 'Explain how an exponential function and its logarithmic inverse are related.'),
]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app._gemini = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError('Unexpected model call in subject-template render test')
    )
    for name, template_id, params, question in CASES:
        template = templates.get(template_id)
        assert template, template_id
        tikz = templates.fill(template, params, target='worksheet')
        assert '__' not in tikz, (template_id, tikz)
        req = app.GenerateReq(
            title=question, brief='', subject='Mathematics',
            target='worksheet', theme='mono', format='png',
        )
        rendered = app._verified_render(req, tikz, source='catalog:test', run_critic=False)
        assert rendered.get('ok'), (name, rendered.get('error'), rendered.get('log'))
        (output / f'{name}.png').write_bytes(base64.b64decode(rendered['base64']))
        print(name, template_id)


if __name__ == '__main__':
    main()
