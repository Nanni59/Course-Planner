"""Render-based label-collision audit of the catalog and the exact renderers.

Run with the backend environment (real TeX, poppler):
    python tools/tikz_layout_check.py [--variants]

Every template is compiled through the backend's own _render with the layout
check on (labels crossed by lines, labels overlapping each other, read from the
compiled picture); --variants adds parameter sets that exercise the templates'
geometry-dependent label placement. No model calls are made. Exit 0 = clean.
"""
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
    from hf_space_tikz import templates
    from hf_space_tikz.catalog import elementary

# Parameter sets that move labels around; some still collide (the audit says so).
VARIANTS = {
    'parabola_transformation': [{'A': '-0.5', 'H': '-1', 'K': '3'}, {'A': '2', 'H': '2', 'K': '-1'},
                                {'A': '1', 'H': '-2', 'K': '1'}, {'A': '0.5', 'H': '0', 'K': '-1'}],
    'unit_circle_reference_angle': [{'THETA': t, 'THETA_LABEL': f'${t}^\\circ$', 'REF_LABEL': '$\\alpha$'}
                                    for t in ('45', '135', '210', '300', '160')],
    'vector_linear_combination': [{'ANG': '120', 'NEGANG': '-60', 'ANGLAB': '120^\\circ'},
                                  {'ANG': '40', 'NEGANG': '-140', 'ANGLAB': '40^\\circ'}],
    'vector_resultant_from_angle': [{'ANG': a, 'ANGLAB': f'{a}^\\circ'} for a in ('30', '60', '110')],
    'vector_difference_from_angle': [{'ANG': a, 'ANGLAB': f'{a}^\\circ'} for a in ('25', '45', '140')],
    'airplane_wind_ground_velocity': [{'AIRANG': '20', 'WINDANG': '90', 'BEARING_MID': '55', 'BEARINGLAB': '70^\\circ'},
                                      {'AIRANG': '100', 'WINDANG': '0', 'BEARING_MID': '95', 'BEARINGLAB': '10^\\circ'},
                                      {'AIRANG': '45', 'WINDANG': '180', 'BEARING_MID': '67.5', 'BEARINGLAB': '45^\\circ'}],
    'function_tangent': [{'CURVE': 'sqrt(x)', 'XMIN': '0', 'XMAX': '6', 'YMIN': '-0.5', 'YMAX': '3',
                          'POINT_X': '4', 'POINT_Y': '2', 'SLOPE': '0.25', 'INTERCEPT': '1', 'LABEL_X': '1'},
                         {'CURVE': '-x^2+4', 'XMIN': '-3', 'XMAX': '3', 'YMIN': '-4', 'YMAX': '6',
                          'POINT_X': '1', 'POINT_Y': '3', 'SLOPE': '-2', 'INTERCEPT': '5', 'LABEL_X': '2'}],
    '3d_vector_components': [dict(zip(('XVAL', 'YVAL', 'ZVAL', 'XVALLABEL', 'YVALLABEL', 'ZVALLABEL'), v.split(',') * 2))
                             for v in ('3,4,5', '4,-2,3', '-2,3,2')],
    'circle_chord_arc': [{'ANGLE': '50', 'ARCMID': '25', 'ANGLELAB': '50^\\circ'},
                         {'ANGLE': '140', 'ARCMID': '70', 'ANGLELAB': '140^\\circ'}],
    'sinusoid_amplitude_period': [{'AMPLITUDE_VALUE': '3', 'FREQUENCY_VALUE': '1', 'PHASE_SHIFT_VALUE': '0', 'MIDLINE_VALUE': '-2'},
                                  {'AMPLITUDE_VALUE': '2', 'FREQUENCY_VALUE': '2', 'PHASE_SHIFT_VALUE': '-0.7854', 'MIDLINE_VALUE': '1'}],
    'asymptotes_graph': [{'C': '-2', 'K': '1'}, {'C': '2', 'K': '-1.5'}],
    'rational_asymptotes': [{'A': '7', 'H': '3', 'K': '2'}, {'A': '-7', 'H': '-2', 'K': '3'}],
    'poly_roots_end': [{'ROOTA': '-4', 'ROOTB': '1', 'ROOTC': '5', 'LABELA': '$-4$', 'LABELB': '$1$', 'LABELC': '$5$'}],
}
MIDPOINTS = [
    'Points A(-4, 1) and B(2, 5). Find the midpoint of AB. Diagram: Show both axes from -5 to 5.',
    'Points P(3, -2) and Q(-3, 4). Find the midpoint of PQ. Diagram: Show both axes from -5 to 5.',
    'Points M(-4, -3) and N(4, -1). Find the midpoint of MN. Diagram: Show both axes from -5 to 5.',
]


def audit(name, tikz_options):
    """Like the backend: the first label placement without collisions wins."""
    summary = ''
    for tikz in tikz_options:
        out = app._render(app.RenderReq(code=tikz, format='png', theme='mono', target='worksheet', layout=True))
        if not out.get('ok'):
            return f'{name}: render failed: {out.get("error")}'
        if 'layout' not in out:
            return f'{name}: no layout report'
        if not out['layout']['issues']:
            return None
        summary = summary or app._layout_summary(out['layout'])
    return f'{name}: {summary}'


def fills(template, params):
    return [templates.fill(template, params, target='worksheet', alternative=i) for i in range(templates.alternatives(template))]


def main():
    cases = [(t['id'], fills(t, {})) for t in templates.TEMPLATES]
    breadth = json.loads((ROOT / 'tools/fixtures/worksheet_topic_breadth.json').read_text(encoding='utf-8'))
    for case in breadth:
        hit = elementary.generate(case['question'] + '\nDiagram: ' + case['brief'])
        if hit:
            cases.append(('elementary:' + case['id'], [hit['tikz']]))
    if '--variants' in sys.argv:
        for tid, sets in VARIANTS.items():
            cases += [(f'{tid} {params}', fills(templates.get(tid), params)) for params in sets]
        cases += [(f'elementary midpoint {q[:24]}', [elementary.generate(q)['tikz']]) for q in MIDPOINTS]
    problems = [p for p in (audit(name, tikz) for name, tikz in cases) if p]
    for problem in problems:
        print(problem)
    print(f'{len(cases) - len(problems)} of {len(cases)} diagrams clean')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
