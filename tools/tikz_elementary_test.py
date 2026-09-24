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
real_gemini = ns['_gemini']

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
def lane_trial(behaviour, prepare=None, max_wait=60):
    clock, calls = [1000.0], []
    def post(url, headers, json, timeout):
        model = url.split('/models/')[1].split(':')[0]
        key = headers['x-goog-api-key']
        calls.append((key, model))
        code, text = behaviour(key, model)
        return FakeResponse(code, text)
    ns.update(GEMINI_KEYS=['k1','k2','k3','k4'], GEMINI_MODELS=['primary','secondary','healthy'],
              GEMINI_MAX_ATTEMPTS=4, GEMINI_DEADLINE=180, GEMINI_MAX_WAIT=max_wait, GEMINI_TIMEOUT=90,
              _lane_state=ns['_new_lane_state'](), _last_success_model=None,
              _last_success_model_lock=threading.Lock(),
              time=SimpleNamespace(time=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0]+s)),
              requests=SimpleNamespace(post=post, exceptions=SimpleNamespace(RequestException=OSError)))
    if prepare:
        prepare()
    try:
        result = real_gemini('fixture')
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
assert 'max(6.2832,6.2832/0.5)' in templates.fill(templates.get('sinusoid_amplitude_period'), {'FREQUENCY_VALUE':'0.5'})

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
