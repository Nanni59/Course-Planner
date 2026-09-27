"""Numerical geometry, routing, and async diagnostic regressions; no API calls."""
import ast
import json
import math
from pathlib import Path
import re
import sys
import threading
from types import SimpleNamespace
import unicodedata

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hf_space_tikz'))
import templates
from catalog.elementary import generate

# Execute production helpers without starting the service or loading web dependencies.
tree = ast.parse((ROOT / 'hf_space_tikz/app.py').read_text(encoding='utf-8-sig'))
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
for node in functions:
    node.decorator_list = []
module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + functions, type_ignores=[])
ns = dict(re=re, math=math, json=json, unicodedata=unicodedata, threading=threading, GEMINI_KEYS=['test-secret'],
          _job_trace=threading.local(), _jobs_lock=threading.Lock(), jobs={}, RenderReq=SimpleNamespace)
exec(compile(ast.fix_missing_locations(module), '<production helpers>', 'exec'), ns)
helper_constants = [n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and (t.id.startswith('_TIKZ_EXCERPT_') or t.id in ('_NUM', '_KEY_TYPOS', '_READINESS_RULES', '_JSON_TEX_WORDS')) for t in n.targets)]
exec(compile(ast.fix_missing_locations(ast.Module(body=helper_constants, type_ignores=[])), '<helper constants>', 'exec'), ns)
real_gemini = ns['_gemini']
real_readiness = ns['_readiness_verdict']
real_choice = ns['_readiness_choice']
real_verified_render = ns['_verified_render']

questions = [
    'Triangle ABC is right-angled at A. AB = 6 cm and AC = 8 cm. Find BC. Diagram: Draw AB vertically and AC horizontally, label the vertices, and label BC as x.',
    'Points P(-3, 2) and Q(4, -2) lie on a coordinate plane. Find the midpoint of PQ. Diagram: Show both axes from -5 to 5. Do not plot the midpoint.',
    'A circle has centre O and radius 5 cm. Point P lies outside the circle, with OP = 13 cm. PT is tangent to the circle at T. Find PT. Label PT = x.',
    'A block experiences four forces: 10 N upward, 10 N downward, 8 N to the right, and 3 N to the left. Find the resultant force. Do not draw the resultant force.',
]
hits = [generate(q) for q in questions]
assert all(hits)
for question, hit in zip(questions, hits):
    req = SimpleNamespace(title=question, brief='Question: '+question, subject='Mathematics and Physics', equation='', target='worksheet')
    assert ns['_semantic_visual_issue'](req, hit['tikz']) is None
    assert ns['_worksheet_answer_safe_tikz'](req, hit['tikz']) == hit['tikz']

triangle, segment, tangent, forces = hits
assert '10' not in triangle['tikz'] and '{$x$}' in triangle['tikz']
assert r'right angle=C--A--B' in triangle['tikz']
assert '(0.5,0)' not in segment['tikz'] and 'axis equal image' in segment['tikz']
x,y = tangent['parameters']['tangent_point']
assert math.isclose(x*x+y*y, 25)
assert math.isclose(x*(13-x)+y*(-y), 0, abs_tol=1e-10), 'radius perpendicular to tangent'
assert '12' not in tangent['tikz'] and '{$x$}' in tangent['tikz']
assert forces['tikz'].count('cp line,->') == 4 and r'5\,' not in forces['tikz']
assert generate(questions[0].replace('6 cm', '9 cm').replace('8 cm', '12 cm'))['parameters']['vertical'] == 9
assert generate(questions[2].replace('5 cm', '3 cm').replace('13 cm', '8 cm'))['parameters']['radius'] == 3

circle_question = (
    'Points A, B, and C lie on the circumference of a circle with center O. '
    'If angle AOB = 80 degrees, what is the measure of angle ACB?'
)
circle_angle = generate(circle_question)
assert circle_angle and circle_angle['template'] == 'circle_central_inscribed_angle'
assert circle_angle['parameters'] == {
    'centre': 'O', 'endpoints': ['A', 'B'], 'inscribed_vertex': 'C', 'central_angle': 80
}
assert r'{angle=A--O--B}' in circle_angle['tikz']
assert r'{angle=A--C--B}' in circle_angle['tikz']
assert '80^\\circ' in circle_angle['tikz'] and '280' not in circle_angle['tikz']
assert '"$?$"' in circle_angle['tikz'] and r'\draw' in circle_angle['tikz']
circle_req = SimpleNamespace(title=circle_question, brief='', subject='Geometry', equation='', target='worksheet')
assert ns['_semantic_visual_issue'](circle_req, circle_angle['tikz']) is None
assert 'exterior 280-degree sector' in ns['_readiness_prompt'](circle_req, circle_angle['tikz'])

circle_variation = (
    'Points P, Q, and R lie on the circumference of a circle with centre M. '
    'Angle PMQ = 120 degrees. Determine angle PRQ.'
)
varied_circle = generate(circle_variation)
assert varied_circle and varied_circle['parameters']['central_angle'] == 120
assert varied_circle['parameters']['centre'] == 'M' and varied_circle['parameters']['inscribed_vertex'] == 'R'
assert generate(circle_question + ' Angle BOA = 80.0 degrees.')['parameters'] == circle_angle['parameters']
for invalid_circle in [
    circle_question + ' Angle BOA = 90 degrees.',
    circle_question.replace('A, B, and C', 'A, B, and D'),
    circle_question.replace('angle ACB', 'exterior angle ACB'),
    circle_question.replace('80 degrees', '175 degrees'),
    circle_question + ' Also determine angle ADB.',
]:
    assert generate(invalid_circle) is None, invalid_circle

raw_arc_circle = r'''\begin{tikzpicture}
\coordinate (O) at (0,0); \coordinate (A) at (0:2); \coordinate (B) at (80:2); \coordinate (C) at (200:2);
\draw (O) circle (2); \draw (0:0.6) arc[start angle=0,end angle=280,radius=.6];
\draw (C)--(A) (C)--(B);
\end{tikzpicture}'''
assert 'exterior 280-degree sector' in ns['_semantic_visual_issue'](circle_req, raw_arc_circle)
wrong_vertex_circle = circle_angle['tikz'].replace('{angle=A--C--B}', '{angle=C--A--B}')
assert 'Missing correct interior angle pic' in ns['_semantic_visual_issue'](circle_req, wrong_vertex_circle)
for invalid in [questions[0].replace('6 cm','6 m'), questions[0].replace('6 cm','-6 cm'),
                questions[2].replace('13 cm','4 cm'), questions[3].replace('3 N to the left','unknown force to the left'),
                'Explain scalar and vector quantities.', 'Solve 3(2x-5)=21.']:
    assert generate(invalid) is None, invalid
assert templates.route(questions[0])['id'] != 'network_graph'
for q in questions[1:]:
    assert templates.route(q) is None
    assert templates.route_top(q) == []
assert templates.route('Draw a weighted graph with labelled vertices')['id'] == 'network_graph'
assert templates.route('Draw a plane with a normal vector')['id'] == 'plane_with_normal'

# Broad worksheet topics still arrive as specific generated questions plus an
# internal Diagram description. Specific families must beat generic shared words
# so routine visuals stay on the constrained catalog path instead of spending
# several model calls on a reference-generated replacement.
subject_routes = [
    ('Evaluate the definite integral of x^2 + 1 from x = 0 to x = 2. Diagram: Draw y = x^2 + 1 and shade the area from x = 0 to x = 2.', 'Calculus', 'definite_integral_shaded'),
    ('Use four left-endpoint rectangles to estimate the area under y = x + 1. Diagram: Draw exactly four left-endpoint rectangles.', 'Calculus', 'riemann_sum_rectangles'),
    ('Describe these cumulative frequencies. Diagram: Plot an ogive through the stated upper-class boundaries.', 'Data Management', 'ogive'),
    ('Describe the grouped frequencies. Diagram: Draw a histogram with five class intervals.', 'Data Management', 'histogram'),
    ('Interpret the five-number summary. Diagram: Draw a horizontal box plot.', 'Data Management', 'boxplot'),
    ('Describe the correlation. Diagram: Draw a scatter plot and a line of best fit.', 'Data Management', 'scatter_fit'),
    ('Bottle fills are normally distributed. Diagram: Draw a normal distribution curve and shade one standard deviation.', 'Data Management', 'normal_curve'),
    ('Describe the transformations of an exponential function and its horizontal asymptote.', 'Advanced Functions', 'exponential_asymptote'),
    ('Identify the vertical and horizontal asymptotes of this rational function.', 'Advanced Functions', 'rational_asymptotes'),
    ('Determine the amplitude and period of this sinusoidal function.', 'Advanced Functions', 'sinusoid_amplitude_period'),
    ('Graph f(x)=x+2 for x<1 and f(x)=5-x for x>=1. Diagram: Use an open point and a closed point.', 'Advanced Functions', 'piecewise_linear'),
    ('Explain how an exponential function and its logarithmic inverse are reflected across y=x.', 'Advanced Functions', 'function_inverse_reflection'),
]
for text, subject, expected in subject_routes:
    routed = templates.route(text, subject)
    assert routed and routed['id'] == expected, (expected, (routed or {}).get('id'))

integral_tikz = templates.fill(templates.get('definite_integral_shaded'), {
    'CURVE':'x^2+1', 'XMIN':'-1', 'XMAX':'3', 'YMIN':'0', 'YMAX':'11',
    'A':'0', 'B':'2', 'A_LABEL':'$0$', 'B_LABEL':'$2$',
    'AREA_LABEL_X':'1', 'AREA_LABEL_Y':'2', 'AREA_LABEL':'area',
}, target='worksheet')
assert '{x^2+1}' in integral_tikz and 'domain=0:2' in integral_tikz and '__' not in integral_tikz
riemann_tikz = templates.fill(templates.get('riemann_sum_rectangles'), {
    'CURVE':'x+1', 'XMIN':'0', 'XMAX':'4.5', 'YMIN':'0', 'YMAX':'6',
    'X0':'0', 'X1':'1', 'X2':'2', 'X3':'3', 'X4':'4',
    'H1':'1', 'H2':'2', 'H3':'3', 'H4':'4',
}, target='worksheet')
assert riemann_tikz.count(r'\path[cp fill]') == 4 and 'domain=0:4' in riemann_tikz
assert riemann_tikz.index(r'\addplot') > riemann_tikz.rindex(r'\path[cp fill]')  # the fills no longer hide the curve
# Tree probabilities are labels: a number field cut "4/10" to "4". A model's own
# $...$ around a label inside the slot's math is dropped.
tree_tikz = templates.fill(templates.get('probability_tree'), {'P1': '4/10', 'P2': '$\\frac{6}{10}$', 'P3': '3/9', 'P4': '6/9', 'P5': '0.4', 'P6': '$5/9$'})
assert '{$4/10$}' in tree_tikz and '{$\\frac{6}{10}$}' in tree_tikz and '{$5/9$}' in tree_tikz and '$$' not in tree_tikz
# The network draws AE only with a weight for it (it drew a dashed AE always).
network = templates.get('network_graph')
assert '\\foreach \\w in {}' in templates.fill(network, {}) and '\\foreach \\w in {7}' in templates.fill(network, {'WAE': '7'})
assert 'cp dashed' not in network['skeleton']
# Venn regions the question fills in are givens (the worksheet showed "3 in the
# centre" as ?); an unstated value is still hidden, and "neither" stays guarded
# even when its value equals a stated number (30, 18, 12, 5 both: 5 neither).
venn3 = templates.fill(templates.get('venn_three'), {'V7': '3', 'V1': '12'}, target='worksheet',
                       question='A survey of 50 people asked about tea, coffee, and juice. 3 like all three drinks.')
assert 'at (0,0) {3};' in venn3 and 'at (-2.2,0.6) {?};' in venn3 and 'rectangle' in venn3
venn2 = templates.fill(templates.get('venn_two'), {'VN': '5', 'LU': '$S$'}, target='worksheet',
                       question='In a class of 30 students, 18 play soccer, 12 play basketball, and 5 play both. How many play neither?')
assert 'at (3.6,-1.65) {?};' in venn2 and '{$S$}' in venn2 and 'rectangle' in venn2
# Bar charts name the question's categories and scale to the counts (a fixed
# ymax=10 cut off taller bars); tree branches name their outcomes.
bars = templates.fill(templates.get('bar_chart'), {'D1': '8', 'D2': '15', 'D3': '3', 'D4': '6', 'C1': 'Apples', 'C2': 'Bananas', 'C3': 'Grapes', 'C4': 'Oranges', 'XLABEL': 'Fruit'})
assert 'xticklabels={{Apples},{Bananas},{Grapes},{Oranges}}' in bars and 'ymax={1.15*max(8,15,3,6,1)}' in bars and 'xlabel={Fruit}' in bars and 'Cat' not in bars
tree_labels = templates.fill(templates.get('probability_tree'), {'E1': 'Red', 'E2': 'Blue', 'L1': 'Red', 'L4': 'Blue'})
assert 'label=above:{Red}] at (A)' in tree_labels and 'label=below:{Blue}] at (B)' in tree_labels and 'Outcome' not in tree_labels
histogram_tikz = templates.fill(templates.get('histogram'), {
    'YMAX':'10', 'L1':'0--9', 'L2':'10--19', 'L3':'20--29', 'L4':'30--39', 'L5':'40--49',
    'F1':'3', 'F2':'7', 'F3':'9', 'F4':'5', 'F5':'2',
})
assert 'xticklabels={0--9,10--19,20--29,30--39,40--49}' in histogram_tikz
scatter_tikz = templates.fill(templates.get('scatter_fit'), {
    'X1':'1','Y1':'2','X2':'2','Y2':'3','X3':'3','Y3':'5','X4':'4','Y4':'6','X5':'5','Y5':'8',
})
assert '(5, 8)' in scatter_tikz and scatter_tikz.count('__') == 0
ogive_tikz = templates.fill(templates.get('ogive'), {
    'XMIN':'0','XMAX':'55','YMAX':'35',
    'X1':'10','C1':'2','X2':'20','C2':'8','X3':'30','C3':'17','X4':'40','C4':'24','X5':'50','C5':'30',
})
assert '(50, 30)' in ogive_tikz and 'xmax=55' in ogive_tikz
rational_tikz = templates.fill(templates.get('rational_asymptotes'), {
    'XMIN':'-5','XMAX':'7','YMIN':'-6','YMAX':'10',
    'A':'7','H':'3','K':'2','LABEL_H':'?','LABEL_K':'?',
}, target='worksheet')
# The window derives from A, H, and K rather than model-chosen bounds.
assert 'domain={min(-1,3-6)}:{max(1,3+6)}' in rational_tikz and '__' not in rational_tikz
assert 'XMIN' not in templates.get('rational_asymptotes')['params']
intersection = templates.fill(templates.get('function_intersection_two_curves'), {'F':'x^2','G':'x+2'})
assert '{x^2}' in intersection and '{x+2}' in intersection and '4^x' not in intersection
inverse_tikz = templates.fill(templates.get('function_inverse_reflection'), {
    'BASE':'2','F_LABEL':'$f$','INV_LABEL':'$f^{-1}$',
}, target='worksheet')
assert '{$f$}' in inverse_tikz and '{$f^{-1}$}' in inverse_tikz
# Grids stay light: a dashed grid is indistinguishable from dashed asymptotes and tangents.
assert not [t['id'] for t in templates.TEMPLATES if 'grid style={cp dashed}' in t['skeleton']]
# 3D components: the x-axis view is chosen per vector, so no vector projects onto the origin
# (the old fixed view drew (2, 1.5, 1) as a stub), and the component box is drawn through Q.
vec3d = templates.fill(templates.get('3d_vector_components'), {'XVAL':'2','YVAL':'1.5','ZVAL':'1'}, target='worksheet')
assert 'x={({ifthenelse(' in vec3d and r'\coordinate (Q) at (2,1.5,0);' in vec3d and '__' not in vec3d
def _proj_len(x, y, z, xh, xv):
    return math.hypot(xh*x + y, xv*x + z)
for vec in ((2, 1.5, 1), (2, 1.1, 0.8), (1, 0.55, 0.4), (1, 0.3, 0.75), (3, 4, 5)):
    best = max(_proj_len(*vec, -0.55, -0.4), _proj_len(*vec, -0.3, -0.75))
    assert best >= 0.3 * math.dist(vec, (0, 0, 0)), vec
# Head-to-tail labels sit at their own arrow's midpoint, not piled up on a shared tip.
# (vector_add_head_to_tail places them with \cpsidelabel: segment, far point, fraction)
for tid, mids in (('vector_add_head_to_tail', ('\\cpsidelabel{O}{U}{Vend}{0.5}', '\\cpsidelabel{U}{Vend}{O}{0.5}', '\\cpsidelabel{O}{Vend}{U}{0.5}')),
                  ('vector_subtraction_head_to_tail', ('(O)!0.5!(U)', '(O)!0.5!(V)', '(V)!0.5!(U)'))):
    tikz = templates.fill(templates.get(tid), {}, target='worksheet')
    assert all(m in tikz for m in mids) and not re.search(r'\((?:U|V|Vend)\) node', tikz), tid
assert not templates.catalog_errors()

# Reproduce the September 17 worksheet's question + visualDescription payloads.
# Repeated givens are normal; contradictory repetitions must not be silently used.
retest = [
    (r'Triangle \(DEF\) is right-angled at \(D\). \(DE = 9 \text{cm}\) and \(DF = 12 \text{cm}\). Find \(EF\).',
     r'Draw \(DE\) vertically and \(DF\) horizontally. Label all three vertices \(D\), \(E\), \(F\). Mark the right angle at \(D\). Label \(DE = 9 \text{cm}\), \(DF = 12 \text{cm}\), and \(EF\) as \(x\).'),
    (r'Points \(R(-4, -1)\) and \(S(2, 3)\) lie on a coordinate plane. Find the midpoint of \(RS\).',
     r'Show both axes from \(-5\) to \(5\) with equal unit spacing and numbered ticks. Plot and label points \(R(-4, -1)\) and \(S(2, 3)\) and connect them with a straight segment. Do not mark or label the midpoint.'),
    ('A circle has centre C and radius 6 cm. Point A lies outside the circle, with CA = 10 cm. AT is tangent to the circle at T. Find AT.',
     'Label CT = 6 cm, CA = 10 cm, and AT = x. Mark the right angle at T.'),
    ('A block experiences four forces: 12 N upward, 12 N downward, 11 N to the right, and 4 N to the left. Find the resultant force.',
     r'Draw one block in the center. Draw four force arrows originating from the block, pointing in the stated directions. Label each arrow with its given force: \(12 \text{N}\) upward, \(12 \text{N}\) downward, \(11 \text{N}\) to the right, and \(4 \text{N}\) to the left. Do not draw or label the resultant force.'),
]
retest_texts = [ns['_question_text'](SimpleNamespace(title=q+'\nDiagram: '+d)) for q,d in retest]
retest_hits = [generate(text) for text in retest_texts]
assert [h['template'] for h in retest_hits] == [h['template'] for h in hits]
assert '{$x$}' in retest_hits[0]['tikz'] and '{$?$}' not in retest_hits[0]['tikz']
assert retest_hits[1]['parameters']['points'] == [('R',-4,-1),('S',2,3)]
assert retest_hits[1]['tikz'].count('only marks') == 2
assert r'node[below right,font=\small] at (axis cs:-4,-1)' in retest_hits[1]['tikz']
assert retest_hits[3]['tikz'].count('cp line,->') == 4
assert 'pos=.72' not in retest_hits[2]['tikz']
assert '(0,-2.325)--(3.125,-2.325)' in retest_hits[2]['tikz'], 'dimension stays below circle'
assert generate(retest_texts[0]+' EF = y') is None
assert generate(retest_texts[1]+' R(-4.0, -1.00)')['parameters'] == retest_hits[1]['parameters']
assert generate(retest_texts[1]+' R(-3, -1)') is None
assert generate(retest_texts[1]+' T(0, 0)') is None
assert generate(retest_texts[3]+' 12.00 N upward')['parameters'] == retest_hits[3]['parameters']
assert generate(retest_texts[3]+' 13 N upward') is None
for text, hit in zip(retest_texts, retest_hits):
    req_retest = SimpleNamespace(title=text, brief='Question: '+text, subject='', equation='', target='worksheet')
    assert ns['_semantic_visual_issue'](req_retest, hit['tikz']) is None
    assert ns['_worksheet_answer_safe_tikz'](req_retest, hit['tikz']) == hit['tikz']

# A missing/invalid parameter response cannot silently render catalog defaults.
ns.update(CATALOG_ENABLED=True, FIT_CHECK_ENABLED=True, TEMPLATE_REPAIR_ATTEMPTS=0,
          tcatalog=templates, _gemini=lambda *args,**kwargs: {})
req_catalog = SimpleNamespace(title='Draw a weighted network graph.',brief='',subject='',equation='',target='worksheet')
assert ns['_catalog_generate'](req_catalog) is None

# Compiler/readiness failures survive the reference fallback instead of becoming None.
ns.update(_format_reference_blocks=lambda x: '', _catalog_references=lambda *a,**k: [],
          _gemini=lambda *a,**k: {'tikz': r'\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}'},
          _render=lambda req: {'ok': False, 'error': 'TikZ compile failed.', 'log': 'Undefined control sequence'},
          _job_trace=threading.local())
req = SimpleNamespace(title='Draw a line.', brief='', equation='', subject='', target='worksheet', theme='mono', format='svg')
assert 'Undefined control sequence' in ns['_reference_generate'](req)['error']
def fail_model(*args, **kwargs):
    raise RuntimeError('429 quota exhausted')
ns['_gemini'] = fail_model
assert '429 quota exhausted' in ns['_reference_generate'](req)['error']
assert ns['_readiness_verdict'](req, '')[0] == 'FAIL'

# Render-based layout check (2026-09-27): label boxes come from the compiled
# picture's log, lines from a text-hidden second page. Pure analysis, synthetic input.
layout_constants = [n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id.startswith('_LAYOUT_') for t in n.targets)]
exec(compile(ast.fix_missing_locations(ast.Module(body=layout_constants, type_ignores=[])), '<layout constants>', 'exec'), ns)
assert '\\iftikz@is@matrix' in ns['_LAYOUT_INSTRUMENT'] and 'text opacity=0' in ns['_layout_document']('a\\begin{document}B\\end{document}')
synthetic_log = '\n'.join([
    # a 20x10pt label crossed by a line, two labels overlapping, an empty point, a
    # measuring copy, and a legend (cells then container) that must be skipped
    'CPNODE tikz@f@1 | 10 10 30 10 30 20 10 20 1.0pt 1.0pt N',
    'CPNODE tikz@f@2 | 50 10 70 10 70 20 50 20 1.0pt 1.0pt N',
    'CPNODE tikz@f@3 | 60 12 80 12 80 22 60 22 1.0pt 1.0pt N',
    'CPNODE tikz@f@4 | 90 10 93 10 93 13 90 13 1.5pt 1.5pt N',
    'CPNODE cpmX | 0 0 40 0 40 10 0 10 3.3pt 3.3pt N',
    'CPNODE tikz@f@6 | 0 0 5 0 5 5 0 5 1pt 1pt M',
    'CPNODE tikz@f@5 | 0 0 100 0 100 40 0 40 1pt 1pt N',
    'CPBBOX 0 0 100 40',
])
nodes, bbox = ns['_layout_nodes'](synthetic_log)
assert [n[0] for n in nodes] == ['tikz@f@1', 'tikz@f@2', 'tikz@f@3', 'tikz@f@4'] and bbox == (0.0, 0.0, 100.0, 40.0)
k = ns['_LAYOUT_DPI'] / 72.27
width, height = int((100 + 12) * k) + 1, int((40 + 12) * k) + 1
pixels = bytearray([255]) * (width * height)
line_x = int((20 + 6) * k)  # a vertical line through the middle of label 1
for yy in range(height):
    pixels[yy * width + line_x] = pixels[yy * width + line_x + 1] = 0
def word(x0, y0, x1, y1, text):  # page-1 word box in bp from the top-left
    to = lambda x, y: ((x + 6) * 72 / 72.27, (40 + 6 - y) * 72 / 72.27)
    (a, b), (c, d) = to(x0, y1), to(x1, y0)
    return (a, b, c, d, text)
words = [word(12, 11, 28, 19, 'A'), word(52, 11, 68, 19, 'B'), word(62, 13, 78, 21, 'C')]
report = ns['_layout_analyse'](synthetic_log, words, (width, height, bytes(pixels)))
assert report['labels'] == 3, report
assert [i['kind'] for i in report['issues']] == ['line-through-label', 'labels-overlap'], report
assert report['issues'][0]['labels'] == ['A'] and report['issues'][1]['labels'] == ['B', 'C']
assert ns['_layout_summary'](report) == 'a line runs through the label "A"; the labels "B" and "C" overlap'
shown = bytearray(pixels)
for x0, x1 in ((14, 26), (52, 58)):  # glyph ink for A and B (clear of C); C draws nothing (covered)
    for yy in range(int((40 + 6 - 18) * k), int((40 + 6 - 12) * k)):
        for xx in range(int((x0 + 6) * k), int((x1 + 6) * k)):
            shown[yy * width + xx] = 0
covered = ns['_layout_analyse'](synthetic_log, words, (width, height, bytes(pixels)), shown=bytes(shown))
assert [i['kind'] for i in covered['issues']] == ['line-through-label', 'label-hidden', 'labels-overlap'], covered
assert covered['issues'][1]['labels'] == ['C'] and 'is covered or cut off' in ns['_layout_summary'](covered)
assert ns['_layout_inset']([(0, 0), (4, 0), (4, 4), (0, 4)], 2.5, 2.5) is None
assert abs(ns['_layout_overlap']([(0, 0), (2, 0), (2, 2), (0, 2)], [(1, 1), (3, 1), (3, 3), (1, 3)]) - 1) < 1e-9
# Model-drawn diagrams spend their one repair on reported collisions (the prompt
# names them), and a colliding draft whose repair fails still gets its readiness check.
prompts, renders = [], []
def layout_gemini(prompt, as_json=False, temperature=0.2):
    prompts.append(prompt)
    return {'tikz': r'\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}'} if as_json else 'PASS'
def layout_render(req):
    renders.append(req)
    if len(renders) == 1:
        return {'ok': True, 'svg': '<svg/>', 'layout': {'labels': 1, 'issues': [{'kind': 'line-through-label', 'labels': ['x = ?'], 'ink': 30}]}}
    return {'ok': True, 'svg': '<svg/>', 'layout': {'labels': 1, 'issues': []}}
ns.update(_gemini=layout_gemini, _render=layout_render, _diagram_spec_prompt=lambda *a, **k: 'plan',
          _visual_prompt=lambda req, repair_log='', **k: 'draw ' + repair_log)
out = ns['_reference_generate'](req)
assert out['ok'] and len(renders) == 2 and all(r.layout for r in renders)
assert any('a line runs through the label "x = ?"' in p for p in prompts)
assert sum(p.startswith('draw') for p in prompts) == 2
renders.clear(); prompts.clear()
def repair_breaks(req):
    renders.append(req)
    if len(renders) == 1:
        return {'ok': True, 'svg': '<first/>', 'layout': {'labels': 1, 'issues': [{'kind': 'labels-overlap', 'labels': ['A', 'B'], 'area': 9}]}}
    return {'ok': False, 'error': 'TikZ compile failed.', 'log': 'Undefined control sequence'}
ns['_render'] = repair_breaks
ns['_job_trace'].events = []
out = ns['_reference_generate'](req)
assert out['ok'] and out['svg'] == '<first/>', out
# both the colliding draft and the repair that broke the compile keep their code
coded = {e['stage']: e.get('tikz', '') for e in ns['_job_trace'].events}
assert '\\draw (0,0)--(1,1);' in coded['layout'] and '\\draw (0,0)--(1,1);' in coded['render-error'], ns['_job_trace'].events
assert not ns['_job_trace'].events[-1].get('tikz')  # a passing readiness verdict carries no code
del ns['_job_trace'].events
# Draft and repair are judged fewer collisions first (the repair on a tie): a
# repair that collides more no longer ships over its draft, and a draft whose
# repair fails readiness still gets judged.
def two_renders(first, second):
    def render(req):
        renders.append(req)
        n = first if len(renders) == 1 else second
        return {'ok': True, 'svg': f'<svg n="{len(renders)}"/>', 'preview_png': f'png{len(renders)}',
                'layout': {'labels': 3, 'issues': [{'kind': 'labels-overlap', 'labels': ['a', 'b'], 'area': 5}] * n}}
    return render
def drafts(prompt, as_json=False, temperature=0.2, images=None):
    prompts.append(prompt)
    return {'tikz': '\\draw (0,0)--(1,%d);' % len(prompts)}
# A colliding draft and its repair get ONE verdict (separate verdicts failed the
# repair's "(?, ?)" and passed the same label in its draft), fewer label problems
# first as A, the repair first on a tie, both pictures attached in that order.
asked = []
def choice(answer):
    def choose(req, codes, images, reports):
        asked.append((codes, images, reports))
        return answer
    return choose
for first, second, answer, shipped, order, note in (
        (1, 3, (0, ''), '<svg n="1"/>', ('png1', 'png2'), 'shipped the draft (1 label problems) over its repair (3)'),
        (2, 0, (0, ''), '<svg n="2"/>', ('png2', 'png1'), None),
        (2, 2, (0, ''), '<svg n="2"/>', ('png2', 'png1'), None),
        (1, 0, (1, ''), '<svg n="1"/>', ('png2', 'png1'), 'shipped the draft (1 label problems) over its repair (0)'),
        (1, 3, (None, 'neither labels the vertex'), None, ('png1', 'png2'), None)):
    renders.clear(); prompts.clear(); asked.clear()
    ns.update(_render=two_renders(first, second), _gemini=drafts, _readiness_choice=choice(answer))
    ns['_job_trace'].events = []
    out = ns['_reference_generate'](req)
    assert len(asked) == 1 and asked[0][1] == order and all(r.preview for r in renders), asked
    assert asked[0][2][0].count('overlap') == min(first, second), asked[0][2]
    if shipped:
        assert out['ok'] and out['svg'] == shipped and 'preview_png' not in out, (first, second, out)
    else:
        assert not out['ok'] and 'neither labels the vertex' in out['error'], out
    notes = [e['detail'] for e in ns['_job_trace'].events if e['stage'] == 'layout-choice']
    assert notes == ([note] if note else []), notes
    verdicts = [e for e in ns['_job_trace'].events if e['stage'] == 'readiness']
    assert len(verdicts) == 1 and (verdicts[0]['detail'] == 'PASS ' + 'AB'[answer[0]] if shipped else True)
    del ns['_job_trace'].events
# A repair that renders nothing usable ships its draft with a layout-choice note.
renders.clear(); prompts.clear()
def draft_then_break(req):
    renders.append(req)
    if len(renders) == 1:
        return {'ok': True, 'svg': '<first/>', 'layout': {'labels': 1, 'issues': [{'kind': 'labels-overlap', 'labels': ['A', 'B'], 'area': 9}]}}
    return {'ok': False, 'error': 'TikZ compile failed.', 'log': 'Undefined control sequence'}
ns.update(_render=draft_then_break, _readiness_verdict=lambda req, code, image=None: ('PASS', ''))
ns['_job_trace'].events = []
assert ns['_reference_generate'](req)['svg'] == '<first/>'
assert [e['detail'] for e in ns['_job_trace'].events if e['stage'] == 'layout-choice'] == ['shipped the draft: its repair produced no usable drawing']
del ns['_job_trace'].events
# A single drawing is judged with its picture, and a shipped one keeps its code.
renders.clear(); prompts.clear()
seen = []
ns.update(_render=two_renders(0, 0), _readiness_verdict=lambda req, code, image=None: seen.append(image) or ('PASS', ''))
ns['_job_trace'].events = []
out = ns['_reference_generate'](req)
assert out['ok'] and seen == ['png1'] and 'preview_png' not in out
passed = [e for e in ns['_job_trace'].events if e['stage'] == 'readiness']
assert passed[-1]['detail'] == 'PASS' and '(1,2);' in passed[-1]['tikz'], passed
del ns['_job_trace'].events
ns.update(_readiness_verdict=real_readiness, _readiness_choice=real_choice)
# The paired verdict: one call, both codes and label reports, pictures in order.
calls_seen = []
def verifier(answer):
    def call(prompt, as_json=False, temperature=0.25, images=None):
        calls_seen.append((prompt, images))
        return answer
    return call
for answer, expected in (('PASS B', (1, '')), ('PASS', (0, '')), ('pass a.', (0, '')), ('FAIL: shading spills', (None, 'FAIL: shading spills'))):
    calls_seen.clear()
    ns['_gemini'] = verifier(answer)
    got = ns['_readiness_choice'](req, ('code A', 'code B'), ('pa', 'pb'), ('the labels "x" and "y" overlap', ''))
    assert got == expected, (answer, got)
    prompt, images = calls_seen[0]
    assert images == ['pa', 'pb'] and 'VERSION A TikZ:\ncode A' in prompt and 'A: the labels "x" and "y" overlap' in prompt and 'B: none' in prompt
# Givens may be labelled: the answer-safety rule no longer rejects a vector the
# question states (the 3D case was rejected twice for showing v = <2, 3, 4>).
assert 'STATED IN THE QUESTION are givens' in ns['_readiness_prompt'](req, 'x') and '(?, ?) are correct' in ns['_readiness_prompt'](req, 'x')
# A request refused with pictures attached is retried once without them.
tries = []
def refuses_pictures(prompt, as_json=False, temperature=0.25, images=None):
    tries.append(images)
    if images:
        raise RuntimeError('Gemini API error 400: image input is not supported')
    return 'PASS'
ns['_gemini'] = refuses_pictures
assert ns['_readiness_verdict'](req, 'code', 'png') == ('PASS', '') and tries == [['png'], None]
ns['_gemini'] = real_gemini
# TeX commands a model leaves unescaped in its JSON keep their backslash: \tiny
# came back as a TAB and "iny" (tick labels read "iny6"). \b and \f are always
# commands, \t \n \r only as known words; an escape JSON does not define is a
# command too; well-formed JSON and real line breaks are untouched.
fix = ns['_json_tex_escapes']
raw = r'{"tikz": "\draw (0,0) node {\tiny 6}; \node {$\frac{1}{2}$} \beta \\node \underline{x} °", "caption": "a\nb\tc\nnode"}'
parsed = json.loads(fix(raw))
assert parsed['tikz'] == '\\draw (0,0) node {\\tiny 6}; \\node {$\\frac{1}{2}$} \\beta \\node \\underline{x} °', parsed
assert parsed['caption'] == 'a\nb\tc\nnode'
good = json.dumps({'tikz': '\\draw (0,0) node {\\tiny 6};\n\\node {$\\frac12$};\t', 'c': 'x\ny'})
assert json.loads(fix(good)) == json.loads(good)
# The wrapper defines the label macros templates rely on.
wrapper = ns['_template']('\\draw (0,0)--(1,0);', 'mono', 'worksheet') if '_template' in ns else ''
assert '\\newcommand{\\cpanglelabel}[5]' in wrapper and '\\newcommand{\\cpsidelabel}[6][0.06]' in wrapper and '\\xdef\\cplabelout' in wrapper
# A slot used only in a template's label placements counts as used.
assert not templates.catalog_errors() and '__LABEL_X__' not in templates.get('function_tangent')['skeleton']
assert '__LABEL_X__' in templates.get('function_tangent')['layout_alternatives'][0]
assert '\\pgfmathsetmacro\\cplx{0.5}' in templates.fill(templates.get('function_tangent'), {'LABEL_X': '0.5'})
# Hyphenated TikZ keys are fixed before compiling; label text is not touched.
assert ns['_fix_key_typos']('grid style={line-width=.1pt, dash-pattern = on 2pt}, node[inner-sep=1pt] {$line-width$}') == \
    'grid style={line width=.1pt, dash pattern = on 2pt}, node[inner sep=1pt] {$line-width$}'
# Characters per text line: a stacked one-digit fraction is one wide, dr/dt two.
assert ns['_layout_line_chars']([(0, 0, 4, 5, '3'), (0, 6, 4, 11, '9')]) == 1
assert ns['_layout_line_chars']([(0, 0, 8, 5, 'dr'), (0, 6, 8, 11, 'dt')]) == 2
assert ns['_layout_line_chars']([(0, 0, 8, 5, 'y'), (10, 0.5, 14, 5.5, '='), (16, 0, 20, 5, '4')]) == 3

# Label placement alternatives: fill picks one; the catalog renderer tries them in
# order when the picture shows collisions, and keeps the first clean one.
parabola = templates.get('parabola_transformation')
assert templates.alternatives(parabola) > 1 and templates.alternatives(templates.get('histogram')) == 1
assert '@@ALT@@' not in templates.fill(parabola, {}) and 'anchor=north west]' in templates.fill(parabola, {}, alternative=6)
assert not templates.catalog_errors()
tried = []
def alt_render(req, tikz, source='', run_critic=True):
    tried.append(tikz)
    clean = len(tried) == 3
    return {'ok': True, 'svg': f'<svg n="{len(tried)}"/>', 'layout': {'labels': 1, 'issues': [] if clean else [{'kind': 'labels-overlap', 'labels': ['a', 'b'], 'area': 5}]}}
ns.update(_verified_render=alt_render, tcatalog=templates)
picked = ns['_catalog_render'](req, parabola, {}, source='catalog:test')
assert picked['svg'] == '<svg n="3"/>' and len(tried) == 3 and len(set(tried)) == 3
tried.clear()
ns['_verified_render'] = lambda req, tikz, source='', run_critic=True: tried.append(tikz) or {'ok': True, 'svg': '<svg/>', 'layout': {'labels': 1, 'issues': []}}
assert ns['_catalog_render'](req, parabola, {}, source='catalog:test')['ok'] and len(tried) == 1  # clean first try: no extra renders
# Collision reports name how many placements a template has; one without
# alternatives adds nothing to its layout event (it used to say "placement 1 collides").
colliding = lambda req, tikz, source='', run_critic=True: {'ok': True, 'svg': '<svg/>', 'layout': {'labels': 1, 'issues': [{'kind': 'labels-overlap', 'labels': ['a', 'b'], 'area': 5}]}}
ns.update(_verified_render=colliding)
ns['_job_trace'].events = []
ns['_catalog_render'](req, templates.get('histogram'), {}, source='catalog:test')
assert ns['_job_trace'].events == []
ns['_catalog_render'](req, parabola, {}, source='catalog:test')
notes = [e['detail'] for e in ns['_job_trace'].events]
n = templates.alternatives(parabola)
assert notes[0] == f'placement 1 of {n} collides' and notes[-1] == 'no clean placement; kept placement 1 (1 collision)' and len(notes) == n + 1
del ns['_job_trace'].events

# The trace keeps the drawing code of failed or colliding attempts, bounded per
# event and per job, whitespace-collapsed and without configured secrets.
ns['_job_trace'].events = []
ns['_diagnostic']('render-error', 'Undefined control sequence', tikz='\\begin{tikzpicture}\n   \\draw   (0,0) -- (1,1) node {test-secret 50\\%}; % recompute: 2+2\n% a whole comment line\n\n\\end{tikzpicture}')
event = ns['_job_trace'].events[0]
assert event['tikz'] == '\\begin{tikzpicture}\n\\draw (0,0) -- (1,1) node {[redacted] 50\\%};\n\\end{tikzpicture}', event
long_code = '\n'.join(f'\\draw (0,{i}) -- (1,{i});' for i in range(400))
ns['_diagnostic']('layout', 'x', tikz=long_code)
kept = ns['_job_trace'].events[1]['tikz']
assert '[...]' in kept and kept.startswith('\\draw (0,0)') and kept.endswith('(1,399);') and len(kept) <= ns['_TIKZ_EXCERPT_CHARS'] + 7
ns['_diagnostic']('layout', 'x', tikz=long_code)
ns['_diagnostic']('layout', 'x', tikz=long_code)  # past the job's budget: the event stays, its code does not
assert 'tikz' in ns['_job_trace'].events[2] and 'tikz' not in ns['_job_trace'].events[3]
assert sum(len(e.get('tikz', '')) for e in ns['_job_trace'].events) <= ns['_TIKZ_EXCERPT_BUDGET']
del ns['_job_trace'].events

# Givens the backend reads from the question rather than trusting the model.
def overrides(question, template_id):
    request = SimpleNamespace(title=question, brief='Question: ' + question, subject='', equation='', target='worksheet')
    return ns['_catalog_local_param_overrides'](request, template_id)
# The model gave v's direction (108 degrees) as the angle between u and v (81.9):
# with 2D components the skeleton draws the true directions instead.
got = overrides('Find the angle between the vectors u = (2, 1) and v = (-1, 3).', 'angle_between_vectors')
assert got == {'ALAB': '\\vec{u}', 'BLAB': '\\vec{v}', 'AX': '2', 'AY': '1', 'BX': '-1', 'BY': '3'}, got
got = overrides('Find the angle between \\vec{a} = \\langle 1, 0, 1 \\rangle and \\vec{b} = <0, 1, 1>.', 'angle_between_vectors')
assert got['ANG'] == '60' and got['AX'] == got['BY'] == '0', got
assert ns['_named_vectors']('Points A = (1, 2) and B = (3, 4); p = [2, −5]') == [('p', (2.0, -5.0))]
assert 'AX' not in overrides('Find the angle between two vectors of 5 N and 3 N at 40 degrees.', 'angle_between_vectors')
# Network weights are read as "AB = 4" too, and a question that lists its edges without AE gets none.
got = overrides('Find a minimum spanning tree for the weighted graph with edges AB = 4, AC = 2, BC = 1, BD = 5, CE = 10, and DE = 2.', 'network_graph')
assert got == {'WAB': '4', 'WAC': '2', 'WBC': '1', 'WBD': '5', 'WCE': '10', 'WDE': '2', 'WAE': ''}, got
assert overrides('Edges: AB 3, EA 6.', 'network_graph') == {'WAB': '3', 'WAE': '6'}
assert overrides('Edges: A–B is 3 and A–E is 6.', 'network_graph') == {'WAB': '3', 'WAE': '6'}
assert overrides('Draw a weighted graph.', 'network_graph') == {}
# Projection, cross product and 3D components read their vectors from the
# question (fixed example vectors drew v = (5, 0) tilted and a x b always up).
got = overrides('Find the vector projection of u = (3, 4) onto v = (5, 0).', 'vector_projection')
assert (got['UX'], got['UY'], got['VX'], got['VY'], got['ULAB']) == ('3', '4', '5', '0', '\\vec{u}'), got
got = overrides('Given u = (3, 4) and v = (5, 0), find the projection of v onto u.', 'vector_projection')
assert (got['UX'], got['UY'], got['VX'], got['VY'], got['PROJLAB']) == ('5', '0', '3', '4', '\\mathrm{proj}_{\\vec{u}}\\vec{v}'), got
got = overrides('Use the cross product to find the area of the parallelogram determined by a = (1, 2, 0) and b = (3, 1, 0).', 'cross_product_parallelogram')
assert [got[k] for k in ('AX', 'AY', 'AZ', 'BX', 'BY', 'BZ')] == ['1', '2', '0', '3', '1', '0'] and got['CROSSLAB'] == '\\vec{a}\\times\\vec{b}', got
threed = 'Sketch the position vector v = (2, 3, 4) in three dimensions and find its magnitude.'
got = overrides(threed, '3d_vector_components')
assert [got[k] for k in ('XVAL', 'YVAL', 'ZVAL', 'XVALLABEL', 'LAB')] == ['2', '3', '4', '2', '\\vec{v}'], got
assert templates.route(threed + '\nDiagram: Draw x, y, and z axes and the vector from the origin to (2, 3, 4) with dashed component guides.', 'Vectors')['id'] == '3d_vector_components'
assert templates.route('Find the magnitude of \\vec{v} = (1, 2, 2).', 'Vectors')['id'] == '3d_vector_components'
assert templates.route('Find the cross product of \\vec{a} = (1, 2, 3) and \\vec{b} = (0, 1, 4).', 'Vectors')['id'] == 'cross_product_parallelogram'
for other in ('Find the unit vector in the direction of \\vec{v} = (2, 3, 4).',
              'Find the angle between \\vec{a} = (1, 2, 3) and \\vec{b} = (0, 1, 4).',
              'Find the volume of the parallelepiped with \\vec{a} = (1, 0, 0), \\vec{b} = (0, 2, 0), \\vec{c} = (1, 1, 3) using the cross product.'):
    assert templates.route(other, 'Vectors') is None, other  # still drawn to order
request = SimpleNamespace(title=threed, brief='Question: ' + threed, subject='', equation='', target='worksheet')
threed_tikz = templates.fill(templates.get('3d_vector_components'), got, target='worksheet')
assert ns['_worksheet_answer_safe_tikz'](request, threed_tikz) == threed_tikz  # the given components stay

# Round 3 found fixed shapes labelled with other values (42 degrees drawn as
# 60, an 8 cm side longer than 11 cm, a 33 degree ladder labelled 72, a 12 km
# leg longer than 18 km). The backend now solves the shape from the givens.
def tri(question, brief=''):
    request = SimpleNamespace(title=question, brief=brief or 'Question: ' + question, subject='', equation='', target='worksheet')
    return ns['_catalog_local_param_overrides'](request, 'triangle_general')
got = tri('In triangle ABC, angle A = 42 degrees, angle B = 71 degrees, and a = 15 cm. Find b.',
          'Draw triangle ABC with angle A = 42 degrees and angle B = 71 degrees marked, side a = 15 cm opposite A, and side b labelled x opposite B.')
# largest angle (B, 71) on top, so the base is the longest side; every label from the question
assert got == {'A': 'C', 'B': 'A', 'C': 'B', 'DEG_A': '67', 'DEG_B': '42', 'AB': 'x', 'AC': '15\\,\\mathrm{cm}',
               'BC': '', 'ANG_A': '', 'ANG_B': '42^\\circ', 'ANG_C': '71^\\circ'}, got
got = tri('In triangle DEF, DE = 8 cm, DF = 11 cm, and angle EDF = 64 degrees. Find EF.',
          'Draw triangle DEF with DE = 8 cm and DF = 11 cm, mark angle EDF = 64 degrees at D, and label EF as x.')
assert (got['A'], got['B'], got['C'], got['DEG_B']) == ('F', 'D', 'E', '64') and abs(float(got['DEG_A']) - 43.82) < 0.01, got
assert (got['AB'], got['AC'], got['BC'], got['ANG_B'], got['ANG_A'], got['ANG_C']) == ('11\\,\\mathrm{cm}', 'x', '8\\,\\mathrm{cm}', '64^\\circ', '', ''), got
# live, the worksheet title carries the drawing notes: "triangle DEF" there read as angle DEF
noted = SimpleNamespace(title='In triangle DEF, DE = 8 cm, DF = 11 cm, and angle EDF = 64 degrees. Find EF.\nDiagram: Draw triangle DEF with DE = 8 cm and DF = 11 cm, mark angle EDF = 64 degrees at D, and label EF as x.',
                        brief='Draw triangle DEF with DE = 8 cm and DF = 11 cm, mark angle EDF = 64 degrees at D, and label EF as x.', subject='', equation='', target='worksheet')
assert ns['_catalog_local_param_overrides'](noted, 'triangle_general')['AC'] == 'x'
got = tri('In triangle PQR, p = 7 cm, q = 9 cm and r = 12 cm. Find the largest angle.')
assert got['ANG_C'] == '?' and got['C'] == 'R' and got['AB'] == '12\\,\\mathrm{cm}', got
assert tri('In triangle XYZ, angle X = 40 degrees and XY = 12 m. Find YZ.') == {'A': 'X', 'B': 'Y', 'C': 'Z', 'AB': '12\\,\\mathrm{m}', 'ANG_A': '40^\\circ'}
angles = ns['_solve_triangle'](('A', 'B', 'C'), {'A': 10.0, 'B': 7.0}, {'A': 50.0})  # SSA, acute case
assert abs(angles['B'] - 32.43) < 0.01 and abs(sum(angles.values()) - 180) < 1e-9, angles
assert ns['_solve_triangle'](('A', 'B', 'C'), {'A': 1.0, 'B': 2.0, 'C': 5.0}, {}) is None  # no such triangle
filled = templates.fill(templates.get('triangle_general'), {'ANG_A': '64^\\circ'}, target='worksheet')
assert 'draw opacity=1] ($(A)' in filled and 'draw opacity=0] ($(B)' in filled  # arcs only where labelled
assert not {'SHOW_A', 'DEG_A'} - set(templates.get('triangle_general')['params']) and 'SHOW_A' not in templates.ai_spec(templates.get('triangle_general'))['keys']
def rt(question):
    request = SimpleNamespace(title=question, brief='Question: ' + question, subject='', equation='', target='worksheet')
    return ns['_catalog_local_param_overrides'](request, 'right_triangle')
assert rt('A 6 m ladder leans against a vertical wall and makes an angle of 72 degrees with the ground. How high up the wall does it reach?') == {'ANGLE_DEG': '72', 'ANGLAB': '72^\\circ', 'TOPANGLAB': ''}
assert rt('A 5 m ladder makes an angle of 20 degrees with the wall. How far is its foot from the wall?') == {'HEIGHTLAB': '', 'ANGLE_DEG': '70', 'ANGLAB': '', 'TOPANGLAB': '20^\\circ'}  # no unasked h
got = overrides('Two boats leave the same harbour at the same time. One travels 12 km on a bearing of 035 degrees and the other travels 18 km on a bearing of 140 degrees. How far apart are they?', 'bearing_two_objects')
assert got == {'B1': '35', 'B2': '140', 'L1': '12\\,\\mathrm{km}', 'L2': '18\\,\\mathrm{km}', 'LEN1': '12', 'LEN2': '18'}, got
got = overrides('Two ships leave port. One sails at 20 km/h on a bearing of 070 and the other at 30 km/h on a bearing of 190. How far apart are they after 2 hours?', 'bearing_two_objects')
assert got == {'B1': '70', 'B2': '190', 'LEN1': '20', 'LEN2': '30', 'L1': '20\\,\\mathrm{km/h}', 'L2': '30\\,\\mathrm{km/h}'}, got
# speed x time is the student's step: legs show speeds, and a distance the question
# does not state becomes a symbol (a model labelled the legs 40 km and 60 km)
hikers = SimpleNamespace(title='Two hikers leave camp on bearings of 050 and 160. How far apart are they?', brief='', subject='', equation='', target='worksheet')
got = ns['_catalog_local_param_overrides'](hikers, 'bearing_two_objects', {'L1': '8\\,\\mathrm{km}', 'L2': 'd_2'})
assert got == {'B1': '50', 'B2': '160', 'L1': 'd_1', 'L2': 'd_2'}, got
# A cosine's phase was the model's to convert; it gave +pi for -pi and the
# graph started at its minimum. The equation is read here.
wave = ns['_sinusoid_from_text']('The depth of water in a harbour is modelled by d(t) = 2 cos(0.5t) + 5.')
assert (wave['A'], wave['B'], wave['D']) == (2.0, 0.5, 5.0) and abs(wave['C'] + math.pi) < 1e-12, wave
assert ns['_sinusoid_from_text']('Sketch y = 4 - sin(3x) for x from 0 to 2pi') == {'A': -1.0, 'B': 3.0, 'C': -0.0, 'D': 4.0}
assert abs(ns['_sinusoid_from_text']('Sketch y = 3sin(2(x - π/4)) - 1.')['C'] - math.pi / 4) < 1e-12
assert ns['_sinusoid_from_text']('y = cos(x) + sin(x)') is None and ns['_sinusoid_from_text']('y = 5 sin(x^2)') is None
assert overrides('d(t) = 2 cos(0.5t) + 5 models the depth.', 'sinusoid_amplitude_period')['PHASE_SHIFT_VALUE'] == '-3.1416'
assert ns['_arith_value']("__import__('os').system('x')", 'x') is None and ns['_arith_value']('2(x - 1)', 'x', 3) == 4.0
assert ns['_arith_pgf'](ns['_arith_tree']('-x^2 + 4x', 'x'), 'x') == '((-(x^2))+(4*x))'  # pgfmath reads -x^2 as (-x)^2
# The model drew a signed-area curve crossing at x = 2 for a stated x = 1.
signed = SimpleNamespace(title='Interpret the integral of f(x) from x = -2 to x = 3 as signed area when f crosses the x-axis at x = 1.',
                         brief='Draw one smooth curve above the x-axis on [-2,1] and below it on [1,3].', subject='', equation='', target='worksheet')
got = ns['_catalog_local_param_overrides'](signed, 'definite_integral_shaded', {'CURVE': '(x+2)*(2-x)', 'A': '-2', 'B': '3'})
curve = ns['_arith_tree'](got['CURVE'], 'x')
assert abs(ns['_arith_eval'](curve, 1.0)) < 1e-12 and ns['_arith_eval'](curve, 0.0) > 0 > ns['_arith_eval'](curve, 2.0), got
assert (got['A'], got['B'], got['EXTRA_TICKS'], got['EXTRA_TICK_LABELS'], got['LF0']) == ('-2', '3', ',1', ',$1$', '0'), got
kept = ns['_catalog_local_param_overrides'](signed, 'definite_integral_shaded', {'CURVE': '(1-x)*(x+3)', 'A': '-2', 'B': '3'})
assert 'CURVE' not in kept  # a model curve that crosses where stated stays
got = overrides('Find the area under f(x) = x^2 + 1 from x = 0 to x = 2.', 'definite_integral_shaded')
assert got['CURVE'] == '((x^2)+1)' and float(got['YMAX']) > 5, got
# a hatch pattern made the SVG too large to ship; below the axis is a darker grey
assert 'pattern=' not in templates.get('definite_integral_shaded')['skeleton'] and 'fill=black!35' in templates.get('definite_integral_shaded')['skeleton']
# the model's curve crossed at the stated x = 1 but upside down
flipped = ns['_catalog_local_param_overrides'](signed, 'definite_integral_shaded', {'CURVE': '0.5*(x-1)*(x+3)', 'A': '-2', 'B': '3'})
assert ns['_arith_eval'](ns['_arith_tree'](flipped['CURVE'], 'x'), 0.0) > 0, flipped
# A given rate was hidden as ?: the guard judges the value after "=".
ripple = 'The radius of a circular ripple increases at 3 cm/s. How fast is the area increasing when the radius is 10 cm?'
got = overrides(ripple, 'related_rates_circle')
assert got == {'DR_LABEL': '$\\frac{dr}{dt}=3\\,\\mathrm{cm/s}$'}, got
request = SimpleNamespace(title=ripple, brief='', subject='Calculus', equation='', target='worksheet')
for label, kept_label in ((r'{$\frac{dr}{dt}=3\text{ cm/s}$}', True), (r'{$\frac{dA}{dt}=60\pi$}', False),
                          (r'{$r=10\,\mathrm{cm}$}', True), (r'{$x=\frac{3}{10}$}', False), (r'{$\frac{dA}{dt}=?$}', True)):
    code = '\\node at (0,0) ' + label + ';'
    assert (ns['_worksheet_answer_safe_tikz'](request, code) == code) == kept_label, label
# A doubled JSON escape printed "4, mathrmm/s"; the boat speed is read from the question.
assert templates.sanitize_label('4\\\\,\\\\mathrm{m/s}') == '4\\,\\mathrm{m/s}'
got = overrides('A boat heads straight across a 200 m wide river at 4 m/s while the current flows downstream at 3 m/s. Find the resultant velocity.', 'boat_current_resultant')
assert (got['BOATLAB'], got['CURRENTLAB'], got['WIDTHLAB']) == ('4\\,\\mathrm{m/s}', '3\\,\\mathrm{m/s}', '200\\,\\mathrm{m}'), got
# An inequality's number line is blank: a drawn circle and arrow was the answer.
assert templates.route('Solve 2x - 3 < 5 and show the solution on a number line.', 'Mathematics')['id'] == 'number_line_blank'
assert overrides('Solve 2x - 3 < 5. Draw a number line from -2 to 8.', 'number_line_blank') == {'XMIN': '-2', 'XMAX': '8'}
assert 'circle' not in templates.get('number_line_blank')['skeleton'] and 'IS the answer' in ns['_READINESS_RULES']
# Live, the arc check meant for model drawings rejected every triangle template.
ladder = SimpleNamespace(title='A 6 m ladder leans against a vertical wall and makes an angle of 72 degrees with the ground.', brief='', subject='', equation='', target='worksheet', format='svg', theme='mono')
ladder_tikz = templates.fill(templates.get('right_triangle'), ns['_catalog_local_param_overrides'](ladder, 'right_triangle'), target='worksheet')
assert ns['_semantic_visual_issue'](ladder, ladder_tikz)  # still guards model drawings
saved_render, saved_enlarge = ns['_render'], ns.get('_enlarge_visual_code')
ns['_render'] = lambda request: {'ok': True, 'svg': '<svg/>', 'layout': {'labels': 4, 'issues': []}}
ns['_enlarge_visual_code'] = lambda request, code: code
assert real_verified_render(ladder, ladder_tikz, source='catalog:right_triangle', run_critic=False)['ok']
assert not real_verified_render(ladder, ladder_tikz, source='draft', run_critic=False)['ok']
ns['_render'], ns['_enlarge_visual_code'] = saved_render, saved_enlarge
# A worksheet's diagram description repeats the question's equation.
wave = ns['_sinusoid_from_text']('d(t) = 2 cos(0.5t) + 5. State the amplitude. Diagram: Graph one cycle of d(t) = 2 cos(0.5t) + 5.')
assert wave is not None and abs(wave['C'] + math.pi) < 1e-12, wave
assert ns['_sinusoid_from_text']('y = 2cos(x) + 1 and y = 3cos(x)') is None
got = overrides('Sketch y = -2cos(x) + 1 over one period and state its range.', 'sinusoid_amplitude_period')
assert (got['AMPLITUDE_LABEL'], got['PERIOD_LABEL'], got['MIDLINE_LABEL']) == ('$A$', '$P$', 'midline'), got
assert 'AMPLITUDE_LABEL' not in overrides('Sketch y = 3sin(x) over one period.', 'sinusoid_amplitude_period')

# Round 4b. The model vetoed the blank number line (the brief asked for the
# circle and shading) and the drawing that replaced it was the answer.
inequality = SimpleNamespace(title='Solve 2x - 3 < 5 and show the solution on a number line.', brief='Draw a number line from -2 to 8 with an open circle at the boundary.',
                             subject='Mathematics', equation='', target='worksheet', format='svg', theme='mono')
saved = {k: ns[k] for k in ('_gemini', '_catalog_render')}
ns['_gemini'] = lambda *args, **kwargs: {'_fit': 'no', '_why': 'the brief asks for a circle and shading'}
ns['_catalog_render'] = lambda request, tmpl, params, source: {'ok': True, 'svg': '<svg/>', 'tikz': templates.fill(tmpl, params, target='worksheet')}
got = ns['_catalog_generate'](inequality)
assert got['ok'] and got['customized'] == 'catalog:number_line_blank' and 'circle' not in got['tikz'], got
ns.update(saved)
assert ns['_number_line_solution'](inequality) and not ns['_number_line_solution'](SimpleNamespace(title='Plot -2, 0.5 and 3 on a number line.'))
# "5 m" as a math label printed an italic 5m
assert '5\\,\\mathrm{m}' in templates.fill(templates.get('right_triangle'), {'HYPLAB': '5 m'}, target='worksheet')
assert templates._upright_unit('2x', True) == '2x' and templates._upright_unit('5 m', False) == '5 m'
# the arc follows its label out (a narrow top angle left its label mid-ladder)
assert '\\cpn{max(\\cpn,min(\\cplabelin-0.1' in templates.get('right_triangle')['skeleton']
# two-leg bearings: legs in proportion, labels beside their own legs
got = overrides('A ship sails 40 km on a bearing of 065 degrees, then 30 km on a bearing of 150 degrees. How far is it from its starting point?', 'bearing_two_leg')
assert (got['LEN1'], got['LEN2'], got['L1']) == ('40', '30', '40\\,\\mathrm{km}'), got
assert templates.alternatives(templates.get('bearing_two_leg')) == 24 and 'midway,above' not in templates.get('bearing_two_leg')['skeleton']
assert ns['_travel_bearing_values_from_text']('Two hikers leave camp on bearings of 050 and 160.') == [50, 160]
# tick labels off the marked points and the window's edge
assert 'xtick={\\cpxa,\\cpxb,...,\\cpxz}' in templates.get('rational_asymptotes')['skeleton']
assert '\\cpdn<\\cpup,270,90' in templates.get('piecewise_linear')['skeleton']
assert templates.alternatives(templates.get('function_tangent')) == 28
assert 'ymax={max(6,__Y1__+1,__Y2__+1)}' in templates.get('secant_and_tangent')['skeleton']
assert templates.alternatives(templates.get('function_inverse_reflection')) == 4
got = ns['_catalog_local_param_overrides'](signed, 'definite_integral_shaded', {'CURVE': '(x+2)*(2-x)', 'A': '-2', 'B': '3'})
assert got['TICK_DOWN'] == 'min(abs(round(\\tick*100)-(300)),1)', got  # the 3 goes above the dark fill
got = overrides('The depth of water is modelled by d(t) = 2 cos(0.5t) + 5. State the amplitude.', 'sinusoid_amplitude_period')
assert got['XVAR'] == 't' and 'cp ticks \\cpq' in templates.get('sinusoid_amplitude_period')['skeleton'], got
# a linear system solved graphically: both lines from the question, no crossing label
system = 'Solve the system y = 2x + 1 and y = -x + 4 graphically.'
assert templates.route(system, 'Mathematics')['id'] == 'function_intersection_two_curves'
assert overrides(system, 'function_intersection_two_curves') == {'XMIN': '-2', 'XMAX': '4', 'F': '((2*x)+1)', 'G': '((-x)+4)', 'F_LABEL': '$y=2x+1$', 'G_LABEL': '$y=-x+4$'}
# The paired verdict records the model that answered and whether it saw the picture.
ns['_job_trace'].last_model, ns['_job_trace'].last_pictured = 'gemini-x', True
assert ns['_verifier_facts']() == {'model': 'gemini-x', 'picture': True} and ns['_verifier_facts']() == {}
assert 'Guide lines, dashed drops, or tick labels that locate an unknown point' in ns['_readiness_prompt'](request, 'x')

# Terminal status always retains the job's own trace, without configured secrets.
def fake_generate(request):
    ns['_diagnostic']('render-error', 'test-secret compiler rejected input', template='fixture')
    return {'ok': False, 'error': 'Compile failed test-secret'}
ns['_generate_visual_sync'] = fake_generate
ns['jobs']['test-job'] = {}
ns['_run_generate_job']('test-job', req)
out = ns['status']('test-job')
assert out['job_id'] == 'test-job' and out['status'] == 'failed'
assert out['diagnostics'][0]['template'] == 'fixture'
assert 'test-secret' not in json.dumps(out)
assert not hasattr(ns['_job_trace'], 'events')
ns['_generate_visual_sync'] = lambda request: {'ok':True,'svg':'<svg/>','customized':'elementary:test'}
ns['jobs']['next-job'] = {}
ns['_run_generate_job']('next-job', req)
assert ns['status']('next-job')['diagnostics'] == []
assert ns['status']('next-job')['source'] == 'elementary:test'
print('PASS elementary geometry, unsupported-input fallback, routing, and failure diagnostics')

# The real frontend payloads, not just isolated question text.
fixtures = json.loads((ROOT / 'tools/fixtures/worksheet_reliability.json').read_text(encoding='utf-8'))
fixture_texts = [ns['_question_text'](SimpleNamespace(title=q['question']+'\nDiagram: '+q['visualDescription'])) for q in fixtures]
fixture_hits = [generate(text) for text in fixture_texts]
assert all(fixture_hits), [(i+1,t) for i,(t,h) in enumerate(zip(fixture_texts,fixture_hits)) if not h]
assert [h['template'] for h in fixture_hits] == ['right_triangle_given_legs','coordinate_segment','quadratic_explicit_bounds','circle_external_tangent','block_four_forces']
curve = fixture_hits[2]
assert curve['parameters'] == dict(a=-1,b=0,c=4,domain=[-3,3],yrange=[-6,5])
assert 'only marks' not in curve['tikz'] and r'\node' not in curve['tikz']
assert 'domain=-3:3' in curve['tikz'] and 'ymin=-6,ymax=5' in curve['tikz']
for text, hit in zip(fixture_texts, fixture_hits):
    request = SimpleNamespace(title=text, brief='Question: '+text, subject='', equation='', target='worksheet')
    assert ns['_semantic_visual_issue'](request, hit['tikz']) is None
    assert ns['_worksheet_answer_safe_tikz'](request, hit['tikz']) == hit['tikz']

suffix = '. Plot over -3 <= x <= 3. Show the y-axis from -6 to 5.'
for equation, expected in [('x^2',(1,0,0)), ('2x^{2}-3x+1',(2,-3,1)), ('-.5x^2',(-.5,0,0)),
                            ('-0.5*x^2+2x-1',(-.5,2,-1)), ('x²+4',(1,0,4)), ('x^2+x',(1,1,0))]:
    hit = generate('Plot the quadratic y = '+equation+suffix)
    if expected is None:
        assert hit is None
    else:
        assert tuple(hit['parameters'][k] for k in ('a','b','c')) == expected
for equation in ['x^3+4','x^2/2','sin(x)','x^2 cos(x)','x^2 z','x^2+2e3','x^2+4z','(x-1)^2','x^2+x+x','0x^2+4','x^2+4; y=x^2+5']:
    assert generate('Plot y = '+equation+suffix) is None, equation
assert generate('Plot y=x^2. Plot domain [-3,3]. Show the y-axis from -6 to 5.')
assert generate(fixture_texts[2]+' Show the y-axis from -6.0 to 5.00.')
for extra in [' Plot over -4 <= x <= 3.', ' Show the y-axis from -7 to 5.', ' Mark the vertex.', ' Draw a tangent line.']:
    assert generate(fixture_texts[2]+extra) is None, extra
assert generate('Plot y=x^2.') is None
assert generate(questions[0]+' AB = 6.00 cm')['parameters'] == triangle['parameters']
assert generate(questions[0]+' AB = 7 cm') is None
assert generate(questions[0]+' Draw AB horizontally.') is None
assert generate(questions[0].replace('AB vertically and AC horizontally','AB should be horizontal and AC should be vertical'))['parameters']['vertical'] == 8
assert generate(questions[1]+' Show both axes from -6 to 5.') is None
assert generate(questions[1]+' Show the x-axis from -6 to 5.') is None
assert generate(questions[1]+' Show the x-axis from -5.0 to 5.00.')
assert generate(questions[3]+' Label the upward arrow 11 N.') is None
assert generate(questions[3]+' Label the rightward arrow 8.00 N.')
assert generate(questions[2]+' OP = 13.0 cm and OT = 5.00 cm')['parameters'] == tangent['parameters']
for extra in [' OP = 14 cm',' OT = 6 cm',' Radius 6 cm',' PT = z',' PT = 12 cm']:
    assert generate(questions[2]+extra) is None, extra
for q in [questions[0].replace('6 cm','12 cm').replace('8 cm','16 cm'),
          questions[1].replace('P(-3, 2)','P(-2, 1)'),
          questions[2].replace('5 cm','4 cm').replace('13 cm','10 cm'),
          questions[3].replace('10 N','12 N').replace('8 N','11 N')]:
    assert generate(q), q
print('PASS five live fixtures, quadratic grammar/bounds, numerical variations and conflicting givens')

# Network errors must be visible in the trace, distinct from HTTP quota errors.
class OfflineError(Exception):
    pass
def offline_post(*args, **kwargs):
    raise OfflineError('test-secret read timed out')
ns.update(GEMINI_MAX_ATTEMPTS=1,GEMINI_MODELS=['fixture'],GEMINI_TIMEOUT=(1,1),GEMINI_DEADLINE=2,
          GEMINI_MAX_WAIT=0,_lane_state=ns['_new_lane_state'](),
          requests=SimpleNamespace(post=offline_post,exceptions=SimpleNamespace(RequestException=OfflineError)),
          time=SimpleNamespace(time=lambda:0,sleep=lambda _:None))
ns['_job_trace'].events = []
try:
    real_gemini('fixture')
    raise AssertionError('Network outage should fail')
except RuntimeError:
    pass
events = ns['_job_trace'].events
assert any(e['stage']=='model-network-error' for e in events)
assert 'test-secret' not in json.dumps(events)
del ns['_job_trace'].events

# Lane scheduler: keys x models. A quota error cools one lane for Google's
# retryDelay, a capacity 503 cools the model on every key, a rejected key cools
# every lane on that key, and a bad request fails at once. Live failures on
# 2026-09-23 spent 12 of 12 attempts on one overloaded model.
class FakeResponse:
    def __init__(self, code, text):
        self.status_code, self.text = code, text
    def json(self):
        return json.loads(self.text)
QUOTA_MINUTE = json.dumps({'error': {'code': 429, 'message': 'You exceeded your current quota', 'details': [
    {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [
        {'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}]},
    {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '21s'}]}})
QUOTA_DAY = QUOTA_MINUTE.replace('PerMinute', 'PerDay')
def lane_trial(behaviour, prepare=None, max_wait=60, models=('primary','secondary','healthy'), as_json=False, bodies=None, images=None):
    clock, calls = [1000.0], []
    def post(url, headers, json, timeout):
        model = url.split('/models/')[1].split(':')[0]
        key = headers['x-goog-api-key']
        calls.append((key, model))
        if bodies is not None:
            bodies.append((model, json))
        code, text = behaviour(key, model)
        return FakeResponse(code, text)
    ns.update(GEMINI_KEYS=['k1','k2','k3','k4'], GEMINI_MODELS=list(models),
              GEMINI_MAX_ATTEMPTS=4, GEMINI_DEADLINE=180, GEMINI_MAX_WAIT=max_wait, GEMINI_TIMEOUT=90,
              _lane_state=ns['_new_lane_state'](), _last_success_model=None,
              _last_success_model_lock=threading.Lock(),
              time=SimpleNamespace(time=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0]+s)),
              requests=SimpleNamespace(post=post, exceptions=SimpleNamespace(RequestException=OSError)))
    if prepare:
        prepare()
    try:
        result = real_gemini('fixture', as_json=as_json, **({'images': images} if images else {}))
    except RuntimeError as exc:
        result = exc
    return result, calls, clock[0] - 1000.0
OK = (200, '{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}')
BUSY = (503, '{"error":{"code":503,"message":"This model is currently experiencing high demand."}}')
# Capacity: one 503 rests the model on every key, so the next attempt moves on.
result, calls, _ = lane_trial(lambda k, m: OK if m == 'healthy' else BUSY)
assert result == 'ok' and [m for _k, m in calls] == ['primary', 'secondary', 'healthy'], calls
# Every model resting (from other jobs): wait for the soonest instead of failing
# or hammering, then use it.
def rest_all():
    for m, s in (('primary', 40), ('secondary', 20), ('healthy', 30)):
        ns['_cool_model'](m, s, 'high demand', 0)
result, calls, elapsed = lane_trial(lambda k, m: OK if m == 'healthy' else BUSY, rest_all)
assert result == 'ok' and 20 <= elapsed <= 60 and len(calls) <= 3, (calls, elapsed)
# ...but a wait longer than the budget fails closed without any request.
result, calls, _ = lane_trial(lambda k, m: OK, rest_all, max_wait=10)
assert isinstance(result, RuntimeError) and not calls and 'cooling down' in str(result)
# Minute quota on the primary for one key: that lane rests for Google's
# retryDelay while the primary stays in use on the other keys.
result, calls, _ = lane_trial(lambda k, m: (429, QUOTA_MINUTE) if (k, m) == ('k1', 'primary') else OK)
assert result == 'ok' and calls == [('k1', 'primary'), ('k2', 'primary')], calls
with ns['_lane_state']['lock']:
    assert round(ns['_lane_wait'](0, 'primary', ns['time'].time())) == 21
    assert ns['_lane_wait'](1, 'primary', ns['time'].time()) == 0
# Daily quota on every key: each key's primary lane rests an hour, then the
# fallback model answers.
result, calls, _ = lane_trial(lambda k, m: (429, QUOTA_DAY) if m == 'primary' else OK)
assert result == 'ok' and [m for _k, m in calls] == ['primary'] * 4 + ['secondary'], calls
assert all(lane['ready_in_s'] == 3600 for lane in ns['_lane_report']() if lane['model'] == 'primary')
# A rejected key rests all of its lanes; a malformed request fails at once.
result, calls, _ = lane_trial(lambda k, m: (403, '{"error":{"message":"permission denied"}}') if k == 'k1' else OK)
assert result == 'ok' and calls == [('k1', 'primary'), ('k2', 'primary')]
assert {l['last_outcome'] for l in ns['_lane_report']() if l['key_slot'] == 1} == {'key rejected'}
result, calls, _ = lane_trial(lambda k, m: (400, '{"error":{"message":"Request payload is invalid"}}'))
assert isinstance(result, RuntimeError) and len(calls) == 1
# Gemma (last-resort free models) is asked without JSON mode, which it may not
# support, and its 400 rests Gemma alone instead of failing the whole call.
REFUSED = (400, '{"error":{"message":"JSON mode is not enabled for models/gemma-4-31b-it"}}')
JSON_OK = (200, '{"candidates":[{"content":{"parts":[{"text":"```json\\n{\\"a\\": 1}\\n```"}]}}]}')
bodies = []
result, calls, _ = lane_trial(lambda k, m: JSON_OK if m == 'gemma-4-31b-it' else (429, QUOTA_DAY),
                              models=('primary', 'gemma-4-31b-it'), as_json=True, bodies=bodies)
assert result == {'a': 1} and calls[-1] == ('k1', 'gemma-4-31b-it'), calls
assert all(('responseMimeType' in b['generationConfig']) == (m == 'primary') for m, b in bodies), bodies
# Pictures go to Gemini models as inline PNG parts; Gemma gets the prompt alone.
bodies = []
result, calls, _ = lane_trial(lambda k, m: OK if m == 'gemma-4-31b-it' else (429, QUOTA_DAY),
                              models=('primary', 'gemma-4-31b-it'), bodies=bodies, images=['aW1n'])
parts = {m: b['contents'][0]['parts'] for m, b in bodies}
assert result == 'ok' and parts['primary'][1] == {'inline_data': {'mime_type': 'image/png', 'data': 'aW1n'}}, parts
assert parts['gemma-4-31b-it'] == [{'text': 'fixture'}], parts
assert ns['_job_trace'].last_model == 'gemma-4-31b-it' and ns['_job_trace'].last_pictured is False
result, calls, _ = lane_trial(lambda k, m: REFUSED if m.startswith('gemma') else OK,
                              models=('gemma-4-31b-it', 'healthy'))
assert result == 'ok' and [m for _k, m in calls] == ['gemma-4-31b-it', 'healthy'], calls
# Repeated capacity failures back off 30 s, then 60 s; a success resets it.
ns['_lane_state'] = ns['_new_lane_state']()
assert ns['_cool_model']('primary', None, 'high demand', 0) == 30
assert ns['_cool_model']('primary', None, 'high demand', 0) == 60
ns['_lane_succeeded'](0, 'primary')
assert ns['_cool_model']('primary', None, 'high demand', 0) == 30
# Parallel jobs spread across keys instead of queueing on the first one.
ns['_lane_state'] = ns['_new_lane_state']()
assert [ns['_pick_lane']()[0] for _ in range(4)] == [0, 1, 2, 3]
assert 'k1' not in json.dumps(ns['_lane_report']())

# Routing diagnostics survive long model-retry traces.
ns['_job_trace'].events = []
ns['_diagnostic']('catalog-route', template='ogive')
for _ in range(20):
    ns['_diagnostic']('model-error', 'busy')
ns['_diagnostic']('catalog-parameter-error', 'Gemini API error 503', template='ogive')
for _ in range(20):
    ns['_diagnostic']('model-error', 'busy')
ns['_diagnostic']('render-error', '(package loading noise)\n' * 40 + '! Undefined control sequence.\nl.12 \\foo')
events = ns['_job_trace'].events
assert len(events) == 24 and events[0]['stage'] == 'catalog-route'
assert [e['stage'] for e in events if not e['stage'].startswith('model-')] == [
    'catalog-route', 'catalog-parameter-error', 'render-error']
assert events[-1]['detail'].startswith('! Undefined control sequence.')
del ns['_job_trace'].events

# Equation-only exponential questions reach the exponential template; calculus
# and inverse questions keep their routes.
for text, expected in [
    ('Describe the transformations and asymptote of y = 2^(x - 1) + 3.', 'exponential_asymptote'),
    ('Graph y = 3(2)^x and state its horizontal asymptote.', 'exponential_asymptote'),
    ('Sketch y = (1/2)^{x} + 1.', 'exponential_asymptote'),
    ('Evaluate the definite integral of e^x from x = 0 to x = 2. Shade the area under the curve.', 'definite_integral_shaded'),
    ('Identify the asymptotes of f(x) = (2x + 1)/(x - 3). Sketch the rational function.', 'rational_asymptotes'),
    ('Explain how y = 2^x and its logarithmic inverse are reflected in y = x.', 'function_inverse_reflection'),
]:
    assert templates.route(text, 'Advanced Functions')['id'] == expected, (text, expected)

# Typographic minus signs and bare decimals keep their value.
assert templates.sanitize_number('\u22122', '9') == '-2'
assert templates.sanitize_number('.5', '9') == '0.5' and templates.sanitize_number('-.25', '9') == '-0.25'

# Template geometry defects found in the 2026-09-23 live review.
inverse_tikz = templates.fill(templates.get('function_inverse_reflection'), {'BASE':'2'})
assert 'coordinates {(1,1)}' not in inverse_tikz and 'coordinates {(0,1) (1,0)}' in inverse_tikz
assert 'bar width=1,' in templates.get('histogram')['skeleton']
assert r'ytick=\empty' in templates.get('boxplot')['skeleton']
normal_skeleton = templates.get('normal_curve')['skeleton']
assert 'scaled y ticks=false' in normal_skeleton
assert normal_skeleton.index(r'\closedcycle') < normal_skeleton.index(r'\addplot[cp line')
integral_skeleton = templates.get('definite_integral_shaded')['skeleton']
assert integral_skeleton.index(r'\closedcycle') < integral_skeleton.index(r'\addplot[cp line')
assert 'AREA_LABEL_X' not in templates.get('definite_integral_shaded')['params']
sinusoid = templates.fill(templates.get('sinusoid_amplitude_period'), {
    'AMPLITUDE_VALUE':'3', 'FREQUENCY_VALUE':'2', 'PHASE_SHIFT_VALUE':'0', 'MIDLINE_VALUE':'-2'})
assert 'sin(deg(2*(x - (0))))' in sinusoid and 'ymin=-4' not in sinusoid
exp_tikz = templates.fill(templates.get('exponential_asymptote'), {'A':'1','B':'2','H':'1','K':'3'})
assert 'pow(2, x - (1))' in exp_tikz and 'ytick={0,1,2,3,4,5}' not in exp_tikz
narrow = generate('Points A, B, and C lie on the circumference of a circle with center O. '
                  'If angle AOB = 20 degrees, what is the measure of angle ACB?')
assert narrow and 'angle eccentricity=1.45' not in narrow['tikz'] and 'angle eccentricity=1.55' not in narrow['tikz']
# Catalog-wide audit (2026-09-23): wrong or unreadable template geometry.
assert templates.sanitize_label('$x = ?$') == '$x = ?$'
unit_circle = templates.fill(templates.get('unit_circle_reference_angle'), {'THETA':'210'})
assert 'angle=B--C--Xaxis' not in unit_circle and '180*round(210/180)' in unit_circle
assert 'scope}[scale=2]' not in unit_circle
for bearing_id in ('bearing_two_leg', 'bearing_two_objects'):
    spec = templates.get(bearing_id)
    assert not {'A1', 'A2', 'M1', 'M2'} & set(spec['params']), bearing_id
    assert '{90-(40)}' in templates.fill(spec, {'B1':'40','B2':'115'})
assert templates.get('bearing_two_leg')['params']['L1']['default'] == ''
cubic = templates.fill(templates.get('poly_roots_end'), {'ROOTA':'-4','ROOTB':'1','ROOTC':'5'})
assert 'xtick={-4,1,5}' in cubic and 'xmin=-4' not in cubic and r'\node[cp label, anchor=north]' not in cubic
logarithm = templates.fill(templates.get('logarithmic_asymptote'), {'H':'3','B':'2'})
assert 'ln(x-(3))' in logarithm and '(0,-2) (0,4)' not in logarithm
assert 'y filter/.expression' in templates.get('rational_asymptotes')['skeleton']
assert '$K_n: every' not in templates.fill(templates.get('complete_graph_sketch'), {})
lin = templates.get('linear_transformation_unit_square')['skeleton']
assert lin.index(r'\draw[cp fill]') < lin.index(r'\draw[cp dashed] (O) -- (U1)')
removable = templates.fill(templates.get('removable_discontinuity'), {'X0':'3','M':'1','B':'3'})
assert '{x+1}' not in removable and 'cpf(3)' in removable
slow_wave = templates.fill(templates.get('sinusoid_amplitude_period'), {'FREQUENCY_VALUE':'0.5'})
assert 'max(6.2832,6.2832/0.5,' in slow_wave
# Label collisions (2026-09-27): the period arrow runs peak to peak instead of
# from the y-axis, and the amplitude label sits mid-arrow instead of on the peak.
assert '(axis cs:0,{' not in slow_wave and '(axis cs:{cpx(0)+cpp(0)},' in slow_wave
assert 'node[pos=.5, anchor=west' in slow_wave and 'node[pos=1, anchor=west' not in slow_wave
# Root labels are drawn once each, on the side of the axis where the curve is not.
assert cubic.count(r'\node[cp label, font=\scriptsize, anchor={ifthenelse(') == 3 and 'xticklabels={}' in cubic
# Asymptote graphs put each tick label on the side of its axis away from the curve.
for tid in ('reciprocal_asymptotes', 'rational_asymptotes'):
    skeleton = templates.get(tid)['skeleton']
    assert r'xticklabel style={anchor={ifthenelse(' in skeleton and r'yticklabel style={anchor={ifthenelse(' in skeleton, tid
    assert '/(\\tick' not in skeleton, tid  # sign tests never divide: pgfmath cannot divide by zero
# Vector labels (2026-09-27): placed beside their own segment, clear by their
# measured size (an invisible copy is typeset to measure it) instead of at fixed
# anchors that let wide labels cross steep vectors.
for tid in ('airplane_wind_ground_velocity', 'boat_current_resultant', 'collinear_vectors',
            'vector_difference_from_angle', 'vector_linear_combination', 'triangle_midpoint_vector_sum',
            'vector_subtraction_as_addition', 'vector_closed_triangle_sum', 'parallelepiped_volume'):
    skeleton = templates.get(tid)['skeleton']
    assert 'overlay,opacity=0]' in skeleton and '.north east)-(' in skeleton, tid
# Comments count as TikZ: none in a vector template may look like a raw arc path,
# or the vector-angle guard rejects the diagram (the bearing arc is exempt there).
for t in templates.TEMPLATES:
    if t['subject'].startswith('Vectors') and t['id'] != 'airplane_wind_ground_velocity':
        assert not re.search(r"\barc\s*(?:\[|\()", t['skeleton']), t['id']
# The line passes through the marked intersection point, and plane labels no
# longer sit under the normal / on the point.
line_plane = templates.get('line_plane_intersection')['skeleton']
assert '($(I)+(-1.2,-1.5,1.3)$)' in line_plane and '($(I)+(1.2,1.5,-1.3)$)' in line_plane
for tid in ('line_plane_intersection', 'plane_with_normal'):
    assert r'\node[cp label] at ($(A)!0.5!(B)$)' not in templates.get(tid)['skeleton'], tid
# Midpoint labels extend toward the grid's middle on the side the segment does not
# use (a fixed "above right" was crossed by rising segments), and continue the
# segment instead where that side would meet the axis tick labels.
rising = generate('Points A(-4, 1) and B(2, 5). Find the midpoint of AB. Diagram: Show both axes from -5 to 5.')['tikz']
assert r'\node[left,font=\small] at (axis cs:-4,1)' in rising and r'\node[above right,font=\small] at (axis cs:2,5)' in rising
# Angle labels are explicit nodes where the angle is computed: the angles library
# splices angle eccentricity into a polar radius, where only a plain number behaves.
for t in templates.TEMPLATES:
    assert 'angle eccentricity={' not in t['skeleton'], t['id']
# Middle axes put the axis letters beyond the arrow tips, clear of the last tick label.
for t in templates.TEMPLATES:
    if 'axis lines=middle' in t['skeleton'] or 'axis lines=center' in t['skeleton']:
        assert 'xlabel style={anchor=west}, ylabel style={anchor=south}' in t['skeleton'], t['id']

# Fifty specific questions across topics, written like generated worksheet
# items (question + model-authored diagram description), must reach the right
# family before any model call: an exact renderer, a catalog template, or the
# verified custom path.
def expected_path(case):
    text = ns['_question_text'](SimpleNamespace(title=case['question'] + '\nDiagram: ' + case['brief']))
    exact = generate(text)
    if exact:
        return 'elementary:' + exact['template']
    routed = templates.route(text, case['subject'])
    if not routed and ns['_looks_like_triangle'](text):
        triangle = templates.get('triangle_general')
        routed = triangle if templates._compatible(triangle, text.lower()) else None
    return 'catalog:' + routed['id'] if routed else 'reference'
breadth = json.loads((ROOT / 'tools/fixtures/worksheet_topic_breadth.json').read_text(encoding='utf-8'))
assert len(breadth) == 50
for case in breadth:
    path = expected_path(case)
    assert case['expect'] == 'any' or path in case['expect'].split('|'), (case['id'], path)
assert not templates.catalog_errors()
print('PASS model fallback, pinned routing diagnostics, exponential routing, number parsing, and template geometry')
