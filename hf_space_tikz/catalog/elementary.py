"""Validated elementary diagrams. No model calls, guessed givens, or solved labels.

Parse only complete supported setups into numerical specs; return None for anything
else so the existing reference-guided generator can handle it. Geometry is computed
from the spec, never from model-authored coordinates. Inputs are normalized by app.py.
"""
import math
import re

NUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"


def _n(value):
    return format(float(value), '.6g')


def _label(value, unit=''):
    return _n(value) + (r'\,\mathrm{' + unit + '}' if unit else '')


def _result(kind, spec, body):
    return {'template': kind, 'parameters': spec,
            'tikz': '\\begin{tikzpicture}\n' + body + '\n\\end{tikzpicture}'}


def _consistent(matches):
    """Accept repeated numerical givens, never pick one of conflicting values."""
    values = {(float(value), unit or '') for value, unit in matches}
    return next(iter(values)) if len(values) == 1 else None


def _unknown(text, side):
    labels = set(re.findall(rf'\b(?:{side}|{side[::-1]})\s*(?:=|(?i:as))\s*([a-z])\b', text))
    return next(iter(labels), '?') if len(labels) <= 1 else None


def _triangle(text):
    name = re.search(r'(?i:triangle)\s+([A-Z]{3})\b', text)
    right = re.search(r'(?i:right[- ]angled at|right angle at)\s+([A-Z])\b', text)
    if not name or not right or right[1] not in name[1] or len(set(name[1])) != 3:
        return None
    if len({frozenset(v) for v in re.findall(r'(?i:triangle)\s+([A-Z]{3})\b', text)}) != 1:
        return None
    if re.search(r'median|bisector|altitude|incircle|circumcircle|rotation|reflect', text, re.I):
        return None
    a = right[1]
    if len(set(re.findall(r'(?i:right[- ]angled at|right angle at)\s+([A-Z])\b', text))) != 1:
        return None
    b, c = [v for v in name[1] if v != a]
    # Respect explicit orientation, including the content model's "should be" form.
    orientations = {}
    for side, orientation in re.findall(r'\b([A-Z]{2})\s+(?:(?:should be|is)\s+)?(vertical(?:ly)?|horizontal(?:ly)?)\b', text):
        side = ''.join(sorted(side))
        orientation = orientation[:1]
        if side in orientations and orientations[side] != orientation:
            return None
        orientations[side] = orientation
    if orientations.get(''.join(sorted(a+b))) == 'h' or orientations.get(''.join(sorted(a+c))) == 'v':
        b,c = c,b
    if any(orientations.get(''.join(sorted(side)), expected) != expected for side,expected in [(a+b,'v'),(a+c,'h')]):
        return None
    def length(v):
        matches = re.findall(rf'\b(?:{a}{v}|{v}{a})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b', text)
        return _consistent(matches)
    vb, vc = length(b), length(c)
    if not vb or not vc or vb[1] != vc[1]:
        return None
    vertical, horizontal = float(vb[0]), float(vc[0])
    if not (0 < vertical < 1e5 and 0 < horizontal < 1e5 and .15 <= vertical / horizontal <= 6):
        return None
    # A separately given hypotenuse or an extra construction needs the general path.
    if re.search(rf'\b(?:{b}{c}|{c}{b})\s*=\s*{NUM}', text):
        return None
    s = 4.2 / max(vertical, horizontal)
    x, y = _n(horizontal*s), _n(vertical*s)
    hyp = _unknown(text, b+c)
    if hyp is None:
        return None
    return _result('right_triangle_given_legs', dict(vertices=[a,b,c], vertical=vertical, horizontal=horizontal, unit=vb[1]), rf'''
\coordinate ({a}) at (0,0); \coordinate ({b}) at (0,{y}); \coordinate ({c}) at ({x},0);
\draw[cp line] ({a})--({b})--({c})--cycle;
\pic[draw=black,angle radius=4mm] {{right angle={c}--{a}--{b}}};
\node[below left] at ({a}) {{${a}$}}; \node[above left] at ({b}) {{${b}$}}; \node[below right] at ({c}) {{${c}$}};
\path ({a})--({b}) node[midway,left] {{${_label(vertical,vb[1])}$}};
\path ({a})--({c}) node[midway,below] {{${_label(horizontal,vc[1])}$}};
\path ({b})--({c}) node[midway,above right] {{${hyp}$}};''')


def _points(text):
    if not re.search(r'midpoint', text, re.I) or re.search(r'circle|triangle|perpendicular|bisector|reflect|translate|rotate', text, re.I):
        return None
    points = re.findall(rf'\b([A-Z])\s*\(\s*({NUM})\s*,\s*({NUM})\s*\)', text)
    unique = {}
    for p, x, y in points:
        coordinates = (float(x), float(y))
        if p in unique and unique[p] != coordinates:
            return None
        unique[p] = coordinates
    if len(unique) != 2:
        return None
    values = [(p,x,y) for p,(x,y) in unique.items()]
    if values[0][1:] == values[1][1:] or any(abs(v)>1000 for _,x,y in values for v in (x,y)):
        return None
    bounds = {(float(lo), float(hi)) for lo,hi in re.findall(rf'both axes from\s*({NUM})\s*to\s*({NUM})', text, re.I)}
    separate_bounds = re.findall(rf'([xy])\s*[- ]\s*axis\s+from\s*({NUM})\s*to\s*({NUM})', text, re.I)
    if separate_bounds and not bounds and {axis.lower() for axis,_,_ in separate_bounds} != {'x','y'}:
        return None
    bounds.update((float(lo),float(hi)) for _,lo,hi in separate_bounds)
    if len(bounds) > 1:
        return None
    lo, hi = next(iter(bounds)) if bounds else (math.floor(min(0,*(v for _,x,y in values for v in (x,y))))-1, math.ceil(max(0,*(v for _,x,y in values for v in (x,y))))+1)
    if not lo < hi or hi-lo > 40 or any(not lo <= v <= hi for _,x,y in values for v in (x,y)):
        return None
    # A label (about two units wide) extends right when it fits inside the grid,
    # else left, on the vertical side the segment does not use; when the segment
    # heads the other way, on the side away from the horizontal axis and its
    # numbered ticks. A fixed "above right" was crossed by rising segments, and
    # leaning toward the middle ran top labels into the y-axis letter.
    def place(x, y, ox, oy):
        horizontal = 'right' if x + 2.2 <= hi else 'left'
        toward_other = (ox > x) == (horizontal == 'right')
        vertical = ('below' if oy > y else 'above') if toward_other and oy != y else ('below' if y < 0 else 'above')
        if abs(y) < 1.3 and (vertical == 'above') == (y < 0):
            # that side runs into the axis tick labels: continue the segment instead
            return 'right' if ox < x else 'left'
        return f'{vertical} {horizontal}'
    marks = '\n'.join(rf'\addplot[only marks,mark=*,mark size=1.5pt] coordinates {{({_n(x)},{_n(y)})}};\node[{place(x, y, ox, oy)},font=\small] at (axis cs:{_n(x)},{_n(y)}) {{${p}({_n(x)},{_n(y)})$}};'
                      for (p,x,y),(_,ox,oy) in zip(values, values[::-1]))
    coords = ' '.join(f'({_n(x)},{_n(y)})' for _,x,y in values)
    return _result('coordinate_segment',dict(points=values,bounds=[lo,hi]),rf'''
\begin{{axis}}[width=7cm,height=7cm,axis equal image,axis lines=middle,xlabel=$x$,ylabel=$y$,xlabel style={{anchor=west}},ylabel style={{anchor=south}},
xmin={_n(lo)},xmax={_n(hi)},ymin={_n(lo)},ymax={_n(hi)},xtick distance=1,ytick distance=1,
tick label style={{font=\small}},grid=major,grid style={{gray!25,thin}},clip=false]
\addplot[cp line] coordinates {{{coords}}};
{marks}
\end{{axis}}''')


def _tangent(text):
    if not re.search(r'circle',text,re.I) or not re.search(r'tangent',text,re.I):
        return None
    centre = re.search(r'cent(?:re|er)\s+([A-Z])\b',text,re.I)
    radius = _consistent(re.findall(rf'radius\s*({NUM})\s*(cm|mm|km|m)?\b',text,re.I))
    tangent = re.search(r'\b([A-Z])([A-Z])\s+is tangent',text)
    if not centre or not radius or not tangent or re.search(r'two tangents|sector|chord|arc|second circle',text,re.I):
        return None
    o, p, t = centre[1].upper(), tangent[1], tangent[2]
    if len(set(re.findall(r'cent(?:re|er)\s+([A-Z])\b',text))) > 1 or len(set(re.findall(r'\b([A-Z]{2})\s+is tangent',text))) > 1:
        return None
    if len({o,p,t}) != 3:
        return None
    radius = _consistent([(str(radius[0]), radius[1])] + re.findall(rf'\b(?:{o}{t}|{t}{o})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b',text))
    distance = _consistent(re.findall(rf'\b(?:{o}{p}|{p}{o})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b',text))
    if not radius or not distance or distance[1] != radius[1]:
        return None
    r,d = radius[0],distance[0]
    if not 0 < r < d < 1e5 or not 1.1 < d/r < 8:
        return None
    tx,ty = r*r/d, r*math.sqrt(d*d-r*r)/d
    s = 5/(r+d)
    lab = _unknown(text, p+t)
    if lab is None or re.search(rf'\b(?:{p}{t}|{t}{p})\s*=\s*{NUM}', text):
        return None
    return _result('circle_external_tangent',dict(radius=r,distance=d,tangent_point=[tx,ty],vertices=[o,p,t]),rf'''
\coordinate ({o}) at (0,0);\coordinate ({p}) at ({_n(d*s)},0);\coordinate ({t}) at ({_n(tx*s)},{_n(ty*s)});
\draw[cp line] ({o}) circle[radius={_n(r*s)}];
\draw[cp line] ({o})--({p});
\draw[thin,gray] (0,-.25)--(0,{_n(-r*s-.65)});
\draw[thin,gray] ({_n(d*s)},-.25)--({_n(d*s)},{_n(-r*s-.65)});
\draw[<->,thin] (0,{_n(-r*s-.45)})--({_n(d*s)},{_n(-r*s-.45)}) node[midway,below] {{${_label(d,distance[1])}$}};
\draw[cp line] ({o})--({t}) node[midway,left] {{${_label(r,radius[1])}$}};
\draw[cp line] ({t})--({p}) node[midway,above right] {{${lab}$}};
\pic[draw=black,angle radius=3mm] {{right angle={o}--{t}--{p}}};
\node[below left] at ({o}) {{${o}$}};\node[right] at ({p}) {{${p}$}};\node[above] at ({t}) {{${t}$}};''')


def _circle_central_inscribed(text):
    """Render the common central/inscribed-angle theorem without model geometry."""
    if not re.search(r'circle|circumference', text, re.I):
        return None
    if re.search(r'exterior angle|reflex angle|major angle|tangent|secant|two circles|cyclic quadrilateral', text, re.I):
        return None
    centres = set(re.findall(r'(?i:cent(?:re|er))\s+([A-Z])\b', text))
    if len(centres) != 1:
        return None
    centre = next(iter(centres))

    point_sets = []
    for clause in re.findall(
        r'(?i:\bpoints?\b)\s+(.{1,100}?)\s+(?i:lie|are)\s+on\s+(?:the\s+)?(?i:circumference|circle)\b',
        text,
    ):
        labels = frozenset(re.findall(r'\b([A-Z])\b', clause))
        if labels:
            point_sets.append(labels)
    if not point_sets or len(set(point_sets)) != 1:
        return None
    circumference = set(point_sets[0])

    angle_token = r'(?:∠|(?i:\bangle\b))\s*([A-Z]{3})'
    given = re.findall(
        angle_token + rf'\s*(?:=|(?i:is|measures?))\s*({NUM})\s*(?i:degrees?)?',
        text,
    )
    central = [(name, value) for name, value in given if name[1] == centre]
    if not central:
        return None
    endpoint_sets = {frozenset((name[0], name[2])) for name, _ in central}
    value = _consistent([(number, '') for _, number in central])
    if len(endpoint_sets) != 1 or value is None:
        return None
    endpoints = next(iter(endpoint_sets))
    theta = float(value[0])
    if len(endpoints) != 2 or not 20 <= theta <= 160:
        return None

    mentioned = set(re.findall(angle_token, text))
    candidates = {
        name for name in mentioned
        if name[1] != centre
        and frozenset((name[0], name[2])) == endpoints
        and set(name) <= circumference
    }
    candidate_keys = {(name[1], frozenset((name[0], name[2]))) for name in candidates}
    if len(candidate_keys) != 1 or not re.search(r'\b(?:find|determine|calculate|what)\b', text, re.I):
        return None
    vertex = next(iter(candidate_keys))[0]
    allowed_keys = {
        (centre, endpoints),
        (vertex, endpoints),
    }
    if any((name[1], frozenset((name[0], name[2]))) not in allowed_keys for name in mentioned):
        return None
    if centre in circumference or not endpoints | {vertex} <= circumference:
        return None

    # Use the central angle's endpoint order to make both TikZ angle pics sweep
    # through the smaller interior sector. Reversing an angle name's endpoints
    # does not change the mathematical angle.
    first_name = central[0][0]
    first, second = first_name[0], first_name[2]
    labels = set()
    for name, label in re.findall(angle_token + r'\s*=\s*([a-z?])\b', text):
        if name[1] == vertex and frozenset((name[0], name[2])) == endpoints:
            labels.add(label)
    if len(labels) > 1:
        return None
    unknown = next(iter(labels), '?')
    half = theta / 2
    # Labels sit on each angle's bisector. They must clear the arc (the central
    # label is horizontal, so its half-width counts; a fixed 1.45 let the arc
    # cut "124°") and reach a point where the wedge is taller than the text (a
    # fixed 1.55 put "?" on a chord of an 18° inscribed angle). Distances in mm.
    def wedge_mm(angle):
        return 1.9 / math.sin(math.radians(angle / 2))
    central_mm = max(6 + 1, wedge_mm(theta)) + 0.9 * len(_n(theta)) + 0.6
    central_eccentricity = _n(round(central_mm / 6, 2))
    inscribed_mm = max(1.55 * 5, wedge_mm(theta / 2) + 1)
    inscribed_eccentricity = _n(round(inscribed_mm / 5, 2))
    # A narrow inscribed angle pushes "?" toward the centre; enlarge the circle
    # so it stops short of the centre label.
    radius = max(2.45, round((inscribed_mm + 8.5) / 10, 2))
    return _result('circle_central_inscribed_angle', {
        'centre': centre,
        'endpoints': [first, second],
        'inscribed_vertex': vertex,
        'central_angle': theta,
    }, rf'''
\coordinate ({centre}) at (0,0);
\coordinate ({first}) at ({_n(-half)}:{_n(radius)});
\coordinate ({second}) at ({_n(half)}:{_n(radius)});
\coordinate ({vertex}) at (180:{_n(radius)});
\draw[cp line] ({centre}) circle[radius={_n(radius)}];
\draw[cp line] ({centre})--({first}) ({centre})--({second});
\draw[cp line] ({vertex})--({first}) ({vertex})--({second});
\pic[draw=black,angle radius=6mm,"${_n(theta)}^\circ$",angle eccentricity={central_eccentricity}] {{angle={first}--{centre}--{second}}};
\pic[draw=black,angle radius=5mm,"${unknown}$",angle eccentricity={inscribed_eccentricity}] {{angle={first}--{vertex}--{second}}};
\fill ({centre}) circle (1.2pt); \fill ({first}) circle (1.2pt); \fill ({second}) circle (1.2pt); \fill ({vertex}) circle (1.2pt);
\node[left] at ({centre}) {{${centre}$}};
\node[below right] at ({first}) {{${first}$}}; \node[above right] at ({second}) {{${second}$}}; \node[left] at ({vertex}) {{${vertex}$}};''')


def _forces(text):
    if not re.search(r'block',text,re.I) or not re.search(r'four forces',text,re.I):
        return None
    if re.search(r'incline|ramp|angle|friction coefficient|pulley',text,re.I):
        return None
    matches = re.findall(rf'({NUM})\s*(?:N|newtons?)\s+(upward|downward|to the right|to the left)\b',text,re.I)
    # Drawing descriptions often reverse the wording: "the upward arrow 12 N".
    aliases = {'upward':'upward','downward':'downward','rightward':'to the right','leftward':'to the left'}
    matches += [(value,aliases[direction.lower()]) for direction,value in re.findall(
        rf'\b(upward|downward|rightward|leftward)\s+arrow\s*(?:as\s+|with\s+)?({NUM})\s*(?:N|newtons?)\b',text,re.I)]
    forces = {}
    for value, direction in matches:
        direction, value = direction.lower(), float(value)
        if direction in forces and forces[direction] != value:
            return None
        forces[direction] = value
    if set(forces)!={'upward','downward','to the right','to the left'} or any(not 0 < v < 1e6 for v in forces.values()):
        return None
    body = r'\draw[cp line] (-.6,-.4) rectangle (.6,.4);\draw[cp line] (-2,-.4)--(2,-.4);'+'\n'
    for direction,start,delta,anchor in [
        ('upward',(0,.4),(0,1),'above'),('downward',(0,-.4),(0,-1),'below'),
        ('to the right',(.6,0),(1,0),'right'),('to the left',(-.6,0),(-1,0),'left')]:
        length = .65 + .75*forces[direction]/max(forces.values())
        end = (start[0]+delta[0]*length,start[1]+delta[1]*length)
        body += rf'\draw[cp line,->] ({start[0]},{start[1]})--({_n(end[0])},{_n(end[1])}) node[{anchor}] {{${_label(forces[direction],"N")}$}};'+'\n'
    return _result('block_four_forces',forces,body)


def _quadratic(text):
    """Strict polynomial grammar and explicit bounds; never evaluate model text."""
    if not re.search(r'parabola|quadratic|graph|plot', text, re.I):
        return None
    if re.search(r'tangent|normal line|shade|inequality|intersection|parent function|second (?:curve|graph)', text, re.I):
        return None
    # Negative drawing instructions are allowed; positive solved annotations aren't.
    instructions = re.sub(r'do not[^.;]*[.;]?', '', text, flags=re.I)
    if re.search(r'(?:mark|label|dot|highlight)\w*[^.;]*(?:vertex|intercept)', instructions, re.I):
        return None
    cleaned = re.sub(r'\^\{\s*2\s*\}', '^2', text.replace('²', '^2'))
    equations = []
    for match in re.finditer(r'\by\s*=\s*', cleaned):
        rhs = re.match(r'[\d.x+\-*/^{}()\\\s]+', cleaned[match.end():])
        if not rhs:
            return None
        remainder = cleaned[match.end()+rhs.end():]
        next_word = re.match(r'[A-Za-z_]+', remainder)
        if next_word and not rhs[0].rstrip().endswith('.'):
            # Whitespace must not make an unsupported factor look like prose.
            if not rhs[0][-1].isspace() or next_word[0].lower() not in {'is','for','over','on','with','where','and','shown'}:
                return None
        expression = re.sub(r'\s+', '', rhs[0]).rstrip('.')
        decimal = r'(?:\d+(?:\.\d+)?|\.\d+)'
        term = rf'(?:{decimal}\*?)?x(?:\^2)?|{decimal}'
        if not re.fullmatch(rf'[+-]?(?:{term})(?:[+-](?:{term}))*', expression):
            return None
        coefficients = [0.0, 0.0, 0.0]
        powers = set()
        for part in re.findall(r'[+-]?[^+-]+', expression):
            power = 2 if 'x^2' in part else 1 if 'x' in part else 0
            if power in powers:
                return None
            powers.add(power)
            coefficient = part.split('x')[0].rstrip('*') if power else part
            coefficients[power] = float(coefficient+'1' if coefficient in ('', '+', '-') else coefficient)
        if not coefficients[2] or any(not math.isfinite(v) or abs(v) > 10000 for v in coefficients):
            return None
        equations.append(tuple(coefficients))
    if not equations or len(set(equations)) != 1:
        return None
    cleaned = cleaned.replace(r'\leq', '<=').replace(r'\le', '<=').replace('≤', '<=')
    domains = re.findall(rf'({NUM})\s*<=\s*x\s*<=\s*({NUM})', cleaned)
    domains += re.findall(rf'(?:domain|x\s*[- ]\s*axis)\s+(?:from\s+)?({NUM})\s*to\s*({NUM})', cleaned, re.I)
    domains += re.findall(rf'domain\s*\[\s*({NUM})\s*,\s*({NUM})\s*\]', cleaned, re.I)
    ranges = re.findall(rf'y\s*[- ]\s*axis\s+from\s*({NUM})\s*to\s*({NUM})', cleaned, re.I)
    xbounds = {(float(lo),float(hi)) for lo,hi in domains}
    ybounds = {(float(lo),float(hi)) for lo,hi in ranges}
    if len(xbounds) != 1 or len(ybounds) != 1:
        return None
    xmin,xmax = next(iter(xbounds))
    ymin,ymax = next(iter(ybounds))
    if any(not lo < hi or hi-lo > 40 or max(abs(lo),abs(hi)) > 1000 for lo,hi in [(xmin,xmax),(ymin,ymax)]):
        return None
    c,b,a = equations[0]
    return _result('quadratic_explicit_bounds', dict(a=a,b=b,c=c,domain=[xmin,xmax],yrange=[ymin,ymax]), rf'''
\begin{{axis}}[width=7cm,height=7cm,axis lines=middle,xlabel=$x$,ylabel=$y$,xlabel style={{anchor=west}},ylabel style={{anchor=south}},
xmin={_n(xmin)},xmax={_n(xmax)},ymin={_n(ymin)},ymax={_n(ymax)},xtick distance=1,ytick distance=1,
tick label style={{font=\small}},grid=major,grid style={{gray!25,thin}},clip=true,clip mode=individual]
\addplot[cp line,no marks,samples=161,domain={_n(xmin)}:{_n(xmax)}] {{{_n(a)}*x^2+({_n(b)})*x+({_n(c)})}};
\end{{axis}}''')


def _seg_dist(px, py, p, q):
    """Distance from point (px, py) to segment pq."""
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / ((dx * dx + dy * dy) or 1)))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)


def _box(text):
    """A rectangular prism from its stated length, width and height, drawn to
    scale, with its space diagonal (and base diagonal) when the question asks.
    A model once drew 3 x 4 x 12 as 3 x 4 x 4 and put the 12 on a 3-long edge."""
    low = text.lower()
    if not re.search(r'\brectangular\s+(?:prism|box|solid)\b|\bcuboids?\b|\bbox\b', low):
        return None
    if re.search(r'\bbox[- ]?(?:and[- ]whisker|plot)|\b(?:cylinder|cone|sphere|pyramid|triangular prism|'
                 r'force|mass|incline|ramp|friction|nets?\b|coordinate|vector)', low):
        return None
    if re.search(r'\b[A-Z]{4,8}\b', text):
        return None  # named vertices ("prism ABCDEFGH") need their letters placed
    unit_re = r'\s*(mm|cm|km|m|in|ft|yd)?\b'
    words = {'l': (r'length|long', r'long'), 'w': (r'width|breadth|wide', r'wide'), 'h': (r'height|tall|high|deep|depth', r'tall|high|deep')}
    found = {k: [] for k in words}
    for key, (nouns, adjectives) in words.items():
        found[key] += re.findall(rf'\b(?:{nouns})\s*(?:of|is|=|:)?\s*({NUM}){unit_re}', low)
        found[key] += re.findall(rf'({NUM}){unit_re}\s*(?:{adjectives})\b', low)
        found[key] += re.findall(rf'\b{key}\s*=\s*({NUM}){unit_re}', low)
    for a, ua, b, ub, c, uc in re.findall(rf'({NUM}){unit_re}\s*(?:by|\u00d7|x|\\times)\s*({NUM}){unit_re}\s*(?:by|\u00d7|x|\\times)\s*({NUM}){unit_re}', low):
        for key, value, unit in zip('lwh', (a, b, c), (ua, ub, uc)):
            found[key].append((value, unit))
    dims, units = {}, set()
    for key, matches in found.items():
        values = {float(v) for v, _u in matches}
        if len(values) != 1:
            return None
        dims[key] = values.pop()
        units |= {u for _v, u in matches if u}
    if len(units) > 1 or not all(0 < v < 1e5 for v in dims.values()):
        return None
    unit = next(iter(units), '')
    base_diag = re.search(r'\b(?:face|base|bottom|floor)\s+diagonal|\bdiagonal\s+of\s+(?:the|a|its|one)\s+(?:base|face|bottom|floor|side)', low)
    space_diag = re.search(r'\bspace\s+diagonal|\bdiagonal\s+of\s+the\s+(?:rectangular\s+)?(?:prism|box|cuboid|solid)'
                           r'|opposite\s+(?:corners|vertices)|\blongest\s+(?:rod|pole|pencil|stick|straw|segment|line|object|diagonal)', low)
    if re.search(r'\bdiagonal', low) and not base_diag:
        space_diag = space_diag or True
    def symbol(kind):
        m = re.search(rf'{kind}diagonal[^.;]{{0,24}}?\b(?:labell?ed(?:\s+as)?|called|named|=)\s*([a-z])\b', low)
        m = m or re.search(rf'{kind}diagonal,?\s+([a-z])(?=\s*[.,;:?)]|\s*$)', low)  # "the space diagonal d."
        return m.group(1) if m else None
    # to scale; a very thin side is drawn at a quarter of the longest so it stays visible
    top = max(dims.values())
    L, W, H = (4.2 * max(dims[k], 0.25 * top) / top for k in 'lwh')
    dx, dy = 0.55 * W * math.cos(math.radians(35)), 0.55 * W * math.sin(math.radians(35))
    pts = {'A': (0, 0), 'B': (L, 0), 'C': (L, H), 'D': (0, H)}
    pts.update({k.lower(): (x + dx, y + dy) for k, (x, y) in list(pts.items())})
    coords = ' '.join(rf'\coordinate ({k}) at ({_n(x)},{_n(y)});' for k, (x, y) in pts.items())
    body = coords + r'''
\draw[cp dashed] (A)--(a)--(b) (a)--(d);
\draw[cp line] (A)--(B)--(C)--(D)--cycle (D)--(d)--(c)--(C) (B)--(b)--(c);
'''
    lab = lambda v: _label(dims[v], unit)
    body += rf'\cpsidelabel{{A}}{{B}}{{D}}{{0.5}}{{${lab("l")}$}}' + '\n'
    body += rf'\cpsidelabel{{B}}{{b}}{{A}}{{0.5}}{{${lab("w")}$}}' + '\n'
    body += rf'\cpsidelabel{{A}}{{D}}{{B}}{{0.5}}{{${lab("h")}$}}' + '\n'
    if base_diag:
        named = symbol(r'(?:face|base|bottom|floor)\s+') or ('?' if not space_diag else '')
        body += r'\draw[cp line,dashed] (A)--(b);' + '\n'
    if space_diag:
        body += r'\draw[cp line,dashed] (A)--(c);' + '\n'
    # Diagonal labels sit on their line with a white knockout (beside it, a thin
    # box left no room), at the point of the middle stretch farthest from every
    # other line: at the midpoint a "?" sat where the diagonal crosses an edge.
    segments = [('A', 'a'), ('a', 'b'), ('a', 'd'), ('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'A'),
                ('D', 'd'), ('d', 'c'), ('c', 'C'), ('B', 'b'), ('b', 'c')]
    segments += [('A', 'b')] * bool(base_diag) + [('A', 'c')] * bool(space_diag)
    def spot(end):
        def gap(t):
            px, py = (pts['A'][0] + t * (pts[end][0] - pts['A'][0]), pts['A'][1] + t * (pts[end][1] - pts['A'][1]))
            return min(_seg_dist(px, py, pts[p], pts[q]) for p, q in segments if (p, q) != ('A', end))
        return max((t / 100 for t in range(30, 71)), key=lambda t: (round(gap(t), 3), -abs(t - 0.5)))
    if base_diag and named:
        body += rf'\node[cp label,fill=white,inner sep=1pt] at ($(A)!{_n(spot("b"))}!(b)$) {{${named}$}};' + '\n'
    if space_diag:
        named = symbol(r'(?:space\s+)?') or '?'
        body += rf'\node[cp label,fill=white,inner sep=1pt] at ($(A)!{_n(spot("c"))}!(c)$) {{${named}$}};' + '\n'
    return _result('rectangular_prism', dict(length=dims['l'], width=dims['w'], height=dims['h'], unit=unit,
                                             space_diagonal=bool(space_diag), base_diagonal=bool(base_diag)), body.rstrip())


# ---- rational functions ---------------------------------------------------------
# A small recursive-descent reader for polynomials in x (numbers, x, x^n, brackets,
# products, sums): coefficient lists, lowest power first. Nothing is evaluated.

def _padd(a, b):
    n = max(len(a), len(b))
    return [(a[i] if i < len(a) else 0.0) + (b[i] if i < len(b) else 0.0) for i in range(n)]


def _pmul(a, b):
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def _ptrim(p):
    p = list(p)
    while len(p) > 1 and abs(p[-1]) < 1e-12:
        p.pop()
    return p


def _pval(p, x):
    return sum(c * x ** i for i, c in enumerate(p))


def _poly(s):
    """Coefficients of a polynomial in x written in s, or None."""
    s = re.sub(r'\\left|\\right|\s+', '', s).replace('\\cdot', '*').replace('{', '(').replace('}', ')')
    pos = [0]

    def peek():
        return s[pos[0]] if pos[0] < len(s) else ''

    def power(p):
        if peek() != '^':
            return p
        pos[0] += 1
        m = re.match(r'\(?(\d)\)?', s[pos[0]:])
        if not m:
            raise ValueError
        pos[0] += m.end()
        out = [1.0]
        for _ in range(int(m.group(1))):
            out = _pmul(out, p)
        return out

    def atom():
        c = peek()
        if c == '(':
            pos[0] += 1
            p = total()
            if peek() != ')':
                raise ValueError
            pos[0] += 1
            return power(p)
        if c == 'x':
            pos[0] += 1
            return power([0.0, 1.0])
        m = re.match(r'\d+(?:\.\d+)?|\.\d+', s[pos[0]:])
        if m:
            pos[0] += m.end()
            return power([float(m.group(0))])
        raise ValueError

    def product():
        p = atom()
        while peek() and (peek() in '(x*' or peek().isdigit()):
            if peek() == '*':
                pos[0] += 1
            p = _pmul(p, atom())
        return p

    def total():
        sign = 1.0
        if peek() in '+-':
            sign = -1.0 if peek() == '-' else 1.0
            pos[0] += 1
        p = [sign * c for c in product()]
        while peek() in ('+', '-') and peek():
            sign = -1.0 if peek() == '-' else 1.0
            pos[0] += 1
            p = _padd(p, [sign * c for c in product()])
        return p

    try:
        p = total()
    except (ValueError, IndexError):
        return None
    p = _ptrim(p)
    return p if pos[0] == len(s) and len(p) <= 5 else None


def _group(s, i, opening='{', closing='}'):
    """(contents, end) of the balanced group opening at s[i], or (None, i)."""
    if i >= len(s) or s[i] != opening:
        return None, i
    depth = 0
    for j in range(i, len(s)):
        depth += {opening: 1, closing: -1}.get(s[j], 0)
        if depth == 0:
            return s[i + 1:j], j + 1
    return None, i


def _rational_at(text, i):
    """(numerator, denominator) coefficients of the fraction written at text[i],
    plus an added constant ("3/(x - 2) + 1"), or None."""
    rest = text[i:].lstrip()
    if rest.startswith('\\frac'):
        num, k = _group(rest, len('\\frac'))
        den, k = _group(rest, k) if num is not None else (None, k)
    else:
        num, k = _group(rest, 0, '(', ')')
        if num is None:
            m = re.match(r'\d*(?:\.\d+)?x(?:\^\d)?(?![\w(])|\d+(?:\.\d+)?', rest)  # 5, x, 2x, x^2
            if not m:
                return None
            num, k = m.group(0), m.end()
        if not rest[k:].lstrip().startswith('/'):
            return None
        k = len(rest) - len(rest[k:].lstrip()) + 1
        k += len(rest[k:]) - len(rest[k:].lstrip())
        den, k = _group(rest, k, '(', ')')
    if num is None or den is None:
        return None
    n, d = _poly(num), _poly(den)
    if not n or not d or len(d) < 2:
        return None
    tail = re.match(r'\s*([-+])\s*(\d+(?:\.\d+)?)(?![\w.(^])', rest[k:])
    if tail:
        n = _padd(n, [(-1 if tail.group(1) == '-' else 1) * float(tail.group(2)) * c for c in d])
    elif re.match(r'\s*[-+*/^(]\s*[\w(\\]', rest[k:]):
        return None  # more follows: not one rational function
    return _ptrim(n), _ptrim(d)


def _pdiv_root(p, r):
    """p / (x - r) by synthetic division (the remainder is dropped)."""
    out = [0.0] * (len(p) - 1)
    carry = 0.0
    for i in range(len(p) - 1, 0, -1):
        carry = p[i] + carry * r if i < len(p) - 1 else p[i]
        out[i - 1] = carry
    return _ptrim(out)


def _real_roots(p):
    """Real roots of a polynomial of degree 1 or 2 (rounded), else None."""
    p = _ptrim(p)
    if len(p) == 2:
        return [-p[0] / p[1]]
    if len(p) == 3:
        c, b, a = p
        disc = b * b - 4 * a * c
        if disc < -1e-9:
            return []
        if abs(disc) <= 1e-9:
            return [-b / (2 * a)]
        q = math.sqrt(disc)
        return sorted([(-b - q) / (2 * a), (-b + q) / (2 * a)])
    return None


def _rational(text):
    """A rational function the question gives, drawn exactly: its vertical,
    horizontal or slant asymptotes dashed and labelled ?, holes as open circles,
    nothing marked at the intercepts. Questions about its features need the
    graph; a model drew these wrong or not at all (a hole, a slant asymptote)."""
    low = text.lower()
    if not re.search(r'\brational\b|\basymptot|\bholes?\b|\bdiscontinuit', low):
        return None
    if re.search(r'[<>≤≥]|\\(?:le|ge|leq|geq|lt|gt)\b|inequalit|number line|\blimit|derivative|\bdomain of the composite', low):
        return None
    if re.search(r'\b(?:empty|blank)\b[^.]{0,40}\b(?:grid|coordinate|axes|plane)\b|\b(?:grid|axes|plane)\b[^.]{0,30}\b(?:empty|blank)\b', low):
        return None  # the description wants a grid for the student to sketch on
    found = []
    for m in re.finditer(r'(?<![A-Za-z])(?:[a-z]\s*\(\s*x\s*\)|y)\s*=', text):
        f = _rational_at(text, m.end())
        if f:
            found.append(tuple(tuple(round(c, 9) for c in part) for part in f))
    if not found or len(set(found)) != 1:
        return None
    num, den = [list(part) for part in found[0]]
    if len(den) > 3 or len(num) > 4:
        return None
    roots = _real_roots(den)
    if roots is None:
        return None
    holes, vas = [], []
    for r in roots:
        if abs(_pval(num, r)) < 1e-7 * max(1.0, max(abs(c) for c in num)):
            num, den = _pdiv_root(num, r), _pdiv_root(den, r)
            holes.append(r)
        else:
            vas.append(r)
    for r in holes:  # a hole whose factor is still in the denominator is an asymptote
        if abs(_pval(den, r)) < 1e-9:
            return None
    n, d = len(num) - 1, len(den) - 1
    if d < 1 and not holes:
        return None
    if n > d + 1:
        return None  # no line asymptote at infinity: not this renderer
    lead = num[-1] / den[-1]
    if d == 0:
        line = None                  # (x^2 - 9)/(x - 3) is a line with a hole: no asymptote
    elif n < d:
        line = (0.0, 0.0)            # y = 0
    elif n == d:
        line = (0.0, lead)
    else:                            # slant: the linear quotient
        quot_slope = lead
        rem = _padd(num, [-quot_slope * c for c in _pmul([0.0, 1.0], den)])
        rem = _ptrim(rem)
        line = (quot_slope, (rem[-1] / den[-1]) if len(rem) - 1 == d else 0.0)
    f = lambda x: _pval(num, x) / _pval(den, x)
    # the window holds the asymptotes, holes, intercepts and origin, 3 units out
    xint = [r for r in (_real_roots(num) or []) if all(abs(r - v) > 1e-6 for v in vas)]
    xs = vas + holes + xint + [0.0]
    xmin, xmax = math.floor(min(xs)) - 3, math.ceil(max(xs)) + 3
    if xmax - xmin < 10:
        pad = (10 - (xmax - xmin)) / 2
        xmin, xmax = math.floor(xmin - pad), math.ceil(xmax + pad)
    if xmax - xmin > 40 or any(abs(v) > 1e3 for v in xs):
        return None
    samples = [xmin + (xmax - xmin) * i / 400 for i in range(401)]
    ys = sorted(f(x) for x in samples if all(abs(x - v) > 0.35 for v in vas) and abs(_pval(den, x)) > 1e-9)
    if len(ys) < 50:
        return None
    lo, hi = ys[len(ys) // 20], ys[-len(ys) // 20 - 1]
    keep = [0.0] + [f(h) for h in holes] + ([f(0.0)] if all(abs(v) > 1e-9 for v in vas) else [])
    if line:
        keep += [line[1], line[0] * xmin + line[1], line[0] * xmax + line[1]]
    lo, hi = min([lo] + keep), max([hi] + keep)
    span = max(hi - lo, 6.0)
    ymin, ymax = math.floor(lo - 0.2 * span), math.ceil(hi + 0.2 * span)
    if ymax - ymin > 60:
        return None
    step = lambda s: 1 if s <= 12 else 2 if s <= 24 else 5
    expr = lambda p: '(' + '+'.join('(' + _n(c) + ')*x^' + str(i) if i else '(' + _n(c) + ')' for i, c in enumerate(p)) + ')'
    fx = expr(num) + '/' + expr(den)
    gap = 0.004 * (xmax - xmin)
    cuts = [xmin] + sorted(vas) + [xmax]
    branches = '\n'.join(
        rf'\addplot[cp line, samples=161, domain={_n(a + (gap if a in vas else 0))}:{_n(b - (gap if b in vas else 0))}] {{{fx}}};'
        for a, b in zip(cuts, cuts[1:]) if b - a > 2 * gap)
    marks = []
    for v in sorted(vas):
        marks.append(rf'\draw[cp dashed] ({{axis cs:{_n(v)},0}}|-{{rel axis cs:0,0}}) -- ({{axis cs:{_n(v)},0}}|-{{rel axis cs:0,1}});')
        marks.append(rf'\node[cp label, anchor=north] at ({{axis cs:{_n(v)},0}}|-{{rel axis cs:0,0}}) {{$x={{?}}$}};')
    m, b = line or (0.0, 0.0)
    if not line:
        pass
    elif m:
        # label where the slant line leaves the window on the right (or the top/bottom)
        xe = xmax if ymin <= m * xmax + b <= ymax else ((ymax if m > 0 else ymin) - b) / m
        marks.append(rf'\addplot[cp dashed, domain={_n(xmin)}:{_n(xmax)}, samples=2] {{{_n(m)}*x+({_n(b)})}};')
        anchor = 'west' if xe >= xmax - 1e-9 else ('south' if m > 0 else 'north')
        marks.append(rf'\node[cp label, anchor={anchor}] at (axis cs:{_n(xe)},{_n(m * xe + b)}) {{$y={{?}}$}};')
    else:
        marks.append(rf'\draw[cp dashed] ({{rel axis cs:0,0}}|-{{axis cs:0,{_n(b)}}}) -- ({{rel axis cs:1,0}}|-{{axis cs:0,{_n(b)}}});')
        # on the x-axis (y = 0) the label goes left of the window, clear of the axis letter
        side, anchor = ('0', 'east') if abs(b) < 1e-9 else ('1', 'west')
        marks.append(rf'\node[cp label, anchor={anchor}] at ({{rel axis cs:{side},0}}|-{{axis cs:0,{_n(b)}}}) {{$y={{?}}$}};')
    for h in holes:
        marks.append(rf'\draw[cp line, fill=white] (axis cs:{_n(h)},{_n(f(h))}) circle[radius=2.2pt];')
    body = rf'''
\begin{{axis}}[width=7.4cm,height=6cm,axis lines=middle,axis line style=cp axis,xlabel={{$x$}},ylabel={{$y$}},
xlabel style={{anchor=west}},ylabel style={{anchor=south}},xmin={_n(xmin)},xmax={_n(xmax)},ymin={_n(ymin)},ymax={_n(ymax)},
xtick distance={step(xmax - xmin)},ytick distance={step(ymax - ymin)},tick label style={{font=\scriptsize}},
grid=major,grid style={{gray!20,thin}},unbounded coords=jump,
y filter/.expression={{abs(y)>{_n(4 * (ymax - ymin) + abs(ymin) + abs(ymax))} ? nan : y}},clip mode=individual]
{branches}
''' + '\n'.join(marks) + r'''
\end{axis}'''
    return _result('rational_function', dict(numerator=num, denominator=den, vertical=sorted(vas), holes=holes,
                                                asymptote=[m, b] if line else None), body)


def generate(text):
    """Return an exact supported numerical setup, otherwise leave custom generation intact."""
    text = text.replace('\u2212', '-').replace('\u2013', '-')
    for parser in (_triangle, _points, _tangent, _circle_central_inscribed, _forces, _quadratic, _box, _rational):
        hit = parser(text)
        if hit:
            return hit
    return None
