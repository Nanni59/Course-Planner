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
ns = dict(re=re, math=math, json=json, unicodedata=unicodedata, GEMINI_KEYS=['test-secret'],
          _job_trace=threading.local(), _jobs_lock=threading.Lock(), jobs={}, RenderReq=SimpleNamespace)
exec(compile(ast.fix_missing_locations(module), '<production helpers>', 'exec'), ns)

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
