r"""Support for parsing expression grammars (PEG)."""

import abc as _abc
import ast as _ast
import dataclasses as _dataclasses
import functools as _functools
import operator as _operator

import regex as _regex

##### Symbols #####

__all__ = [
  'Any', 'BackCapture', 'C', 'Capture', 'Cb', 'Cc', 'Cg', 'Cmt', 'Compound',
  'ConstantCapture', 'Cp', 'Cs', 'Cut', 'FoxyError', 'FunctionCapture',
  'GroupCapture', 'Literal', 'MatchData', 'MatchState', 'MatchTimeCapture',
  'NumberCapture', 'OneOf', 'P', 'Pattern', 'PatternError', 'PositionCapture',
  'Predicate', 'Quantifier', 'R', 'ReductionCapture', 'Regex', 'ScopeCapture',
  'Sequence', 'SimpleCapture', 'V', 'Variable', 'backref', 'compile', 'findall',
  'grammar', 'match', 'options', 'quoted', 'search'
]

__version__ = '1.0.0'

##### API #####

def P(value):
  match value:
    case Pattern(): return value
    case str(): return Literal(value)
    case True: return Any(0)
    case False: return -Any(0)
    case int() if value >= 0: return Any(value)
    case int(): return -Any(-value)
    case dict(): return grammar(value)
    case x if callable(x): return MatchTimeCapture(True, x)
    case _: raise TypeError(value.__type__.__name__)

def compile(pattern, *, defs=None, resolve=True):
  if isinstance(pattern, Pattern):
    return pattern
  if not (m := _meta.match(pattern)):
    raise PatternError('invalid pattern')
  result = m.captures[0]
  if defs is not None:
    if isinstance(result, Pattern):
      raise ValueError('cannot specify defs for an expression pattern')
    result.update(defs)
  return P(result) if resolve else result

def match(pattern, string, start=0, *, defs=None):
  return compile(pattern, defs).match(string, start)

def search(pattern, string, start=0, *, defs=None):
  return compile(pattern, defs).search(string, start)

def findall(pattern, string, start=0, *, defs=None):
  return compile(pattern, defs).findall(string, start)

### Pattern DSL ###

def _takespattern(func):
  @_functools.wraps(func)
  def wrapper(self, other):
    try:
      return func(self, P(other))
    except TypeError:
      return NotImplemented
  return wrapper

class _DSL:
  __slots__ = ()

  @_takespattern
  def __add__(self, other):
    smems = self.members if isinstance(self, Sequence) else (self,)
    omems = other.members if isinstance(other, Sequence) else (other,)
    return Sequence(*smems, *omems)

  @_takespattern
  def __radd__(self, other):
    return other.__add__(self)

  @_takespattern
  def __sub__(self, other):
    return -other + self

  @_takespattern
  def __rsub__(self, other):
    return -self + other

  @_takespattern
  def __or__(self, other):
    smems = self.members if isinstance(self, OneOf) else (self,)
    omems = other.members if isinstance(other, OneOf) else (other,)
    return OneOf(*smems, *omems)

  @_takespattern
  def __ror__(self, other):
    return other.__or__(self)

  def __pow__(self, n):
    match n:
      case int(), int(): return Quantifier(self, *n)
      case int() if n >= 0: return Quantifier(self, n, None)
      case int(): return Quantifier(self, 0, -n)
      case _: return NotImplemented

  def __pos__(self):
    match self:
      case Predicate(): return self
      case _: return Predicate(self, True)

  def __neg__(self):
    match self:
      case Predicate(): return Predicate(self.member, not self.polarity)
      case _: return Predicate(self, False)

  def __rshift__(self, value):
    match value:
      case int() | tuple(): return NumberCapture(self, value)
      case x if callable(x): return FunctionCapture(self, x)
      case _: return NotImplemented

  def __lshift__(self, value):
    match value:
      case x if callable(x): return ReductionCapture(self, x)
      case _: return NotImplemented

##### Internals #####

class _FailType:
  def __bool__(self):
    return False

_CUT = _FailType()
_FAIL = _FailType()

##### Patterns #####

class Pattern(_abc.ABC, _DSL):
  __slots__ = ()

  def match(self, string, start=0):
    if s := self._apply(MatchState(string, start)):
      return MatchData(self, string, start, s.pos, s.captures)

  def search(self, string, start=0):
    for pos in range(start, len(string)):
      if m := self.match(string, pos):
        return m

  def findall(self, string, start=0):
    while m := self.search(string, start):
      start = max(m.end, start + 1)
      yield m

  @_abc.abstractmethod
  def _apply(self, state):
    ...

  def _resolve(self, rules):
    return self

@_dataclasses.dataclass(frozen=True, slots=True)
class MatchState:
  string: str
  pos: int
  cut: bool = False
  captures: tuple = ()

  def succeed(self, pos=None, *, cut=None, captures=None):
    if pos is None:
      pos = self.pos
    if cut is None:
      cut = self.cut
    if captures is None:
      captures = self.captures
    return MatchState(self.string, pos, cut, captures)

  def fail(self):
    return _CUT if self.cut else _FAIL

  def append(self, value):
    return self.succeed(captures=(*self.captures, value))

  def extend(self, values):
    return self.succeed(captures=(*self.captures, *values))

@_dataclasses.dataclass(frozen=True, slots=True)
class MatchData:
  pattern: Pattern
  string: str
  start: int
  end: int
  captures: tuple

  @property
  def match(self):
    return self.string[self.start:self.end]

  def __getitem__(self, key):
    match key:
      case tuple(): return tuple(self.captures[k] for k in key)
      case _: return self.captures[key]

  def __repr__(self):
    caps = (f' {i}:{c!r}' for i, c in enumerate(self.captures))
    return f'<foxy.MatchData {self.match!r}{''.join(caps)}>'

### Atoms ###

class Literal(Pattern):
  __slots__ = ('literal',)

  def __init__(self, literal):
    self.literal = literal

  def _apply(self, state):
    if state.string.startswith(self.literal, state.pos):
      return state.succeed(state.pos + len(self.literal))
    return state.fail()

class Regex(Pattern):
  __slots__ = ('regex',)

  def __class_getitem__(cls, key):
    return cls(f'[{key}]')

  def __init__(self, pattern, flags=0):
    if flags & _regex.V0 == 0:
      flags |= _regex.V1
    self.regex = _regex.compile(pattern, flags)

  def _apply(self, state):
    if m := self.regex.match(state.string, state.pos):
      return state.succeed(m.end(), captures=state.captures + m.groups())
    return state.fail()

R = Regex

class Any(Pattern):
  __slots__ = ('n',)

  def __init__(self, n=1):
    self.n = n

  def _apply(self, state):
    npos = state.pos + self.n
    if npos <= len(state.string):
      return state.succeed(npos)
    return state.fail()

class Cut(Pattern):
  __slots__ = ()

  def _apply(self, state):
    return state.succeed(cut=True)

### Compounds ###

class Compound(Pattern):
  __slots__ = ('members', 'resolved')

  def __init__(self, *members):
    self.members = tuple(map(P, members))
    self.resolved = False

  @property
  def member(self):
    return self.members[0]

  def _resolve(self, rules):
    if not self.resolved:
      self.resolved = True
      self.members = tuple(m._resolve(rules) for m in self.members)
    return self

class Sequence(Compound):
  __slots__ = ()

  def _apply(self, state):
    for m in self.members:
      state = m._apply(state)
      if not state:
        break
    return state

class OneOf(Compound):
  __slots__ = ()

  def _apply(self, state):
    scoped = state.succeed(cut=False)
    for m in self.members:
      s = m._apply(scoped)
      if s is _FAIL:
        continue
      if s is _CUT:
        break
      return s.succeed(cut=state.cut)
    return state.fail()

class Quantifier(Compound):
  __slots__ = ('min_', 'max_')

  def __init__(self, member, min_=0, max_=None):
    super().__init__(member)
    self.min_ = min_
    self.max_ = max_

  def _apply(self, state):
    min_, max_ = self.min_, self.max_
    m, i = self.member, 0
    while max_ is None or i < max_:
      if not (s := m._apply(state)):
        break
      i += 1
      if i > min_ and s.pos == state.pos:
        break
      state = s
    return state if i >= min_ else state.fail()

class Predicate(Compound):
  __slots__ = ('polarity',)

  def __init__(self, member, polarity):
    super().__init__(member)
    self.polarity = bool(polarity)

  def _apply(self, state):
    s = self.member._apply(state)
    flag = bool(s) == self.polarity
    return state if flag else state.fail()

##### Grammars #####

def grammar(rules):
  if not rules:
    raise ValueError('empty grammar')
  for name, patt in rules.items():
    rules[name] = patt._resolve(rules)
  return next(iter(rules.values()))

class Variable(Pattern):
  __slots__ = ('name',)

  def __init__(self, name):
    self.name = name

  def _apply(self, state):
    raise FoxyError(f'unresolved variable {self.name!r}')

  def _resolve(self, rules):
    cur, seen = self, set()
    while isinstance(cur, Variable):
      if cur in seen:
        raise FoxyError(f"circular reference in '{self.name}: {cur.name}'")
      seen.add(cur)
      try:
        cur = rules[cur.name]
      except KeyError as e:
        raise FoxyError(f'undefined rule {cur.name!r}') from e
    return cur

V = Variable

### Captures ###

class Capture(Compound):
  __slots__ = ()

  def __init__(self, member):
    super().__init__(member)

  def _apply(self, state):
    if not (s := self.member._apply(state)):
      return s
    match = state.string[state.pos:s.pos]
    caps = s.captures[len(state.captures):]
    return s.succeed(captures=state.captures + self._capture(match, caps))

  @_abc.abstractmethod
  def _capture(self, match, caps):
    ...

class SimpleCapture(Capture):
  __slots__ = ()

  def _capture(self, match, caps):
    return (match, *caps)

C = SimpleCapture

class BackCapture(Pattern):
  __slots__ = ('n',)

  def __init__(self, n):
    self.n = n

  def _apply(self, state):
    try:
      return state.append(state.captures[self.n])
    except IndexError as e:
      raise FoxyError('capture is out of range') from e

Cb = BackCapture

class ConstantCapture(Pattern):
  __slots__ = ('const', 'factory')

  def __init__(self, const=None, factory=None):
    if const is not None and factory is not None:
      raise ValueError('cannot specify both const and factory')
    self.const = const
    self.factory = factory

  def _apply(self, state):
    return state.append(self.const if self.factory is None else self.factory())

Cc = ConstantCapture

class PositionCapture(Pattern):
  __slots__ = ()

  def _apply(self, state):
    return state.append(state.pos)

Cp = PositionCapture

class GroupCapture(Capture):
  __slots__ = ()

  def _capture(self, match, caps):
    return (caps,)

Cg = GroupCapture

class ScopeCapture(Compound):
  __slots__ = ()

  def __init__(self, member):
    super().__init__(member)

  def _apply(self, state):
    scoped = state.succeed(captures=())
    if not (s := self.member._apply(scoped)):
      return s
    return s.succeed(captures=state.captures + s.captures)

Cs = ScopeCapture

class NumberCapture(Capture):
  __slots__ = ('n',)

  def __init__(self, member, n):
    super().__init__(member)
    self.n = n

  def _capture(self, match, caps):
    try:
      if isinstance(self.n, tuple):
        return tuple(caps[n] for n in self.n)
      return (caps[self.n],)
    except IndexError as e:
      raise FoxyError('capture is out of range') from e

class FunctionCapture(Capture):
  __slots__ = ('func',)

  def __init__(self, member, func):
    super().__init__(member)
    self.func = func

  def _capture(self, match, caps):
    result = self.func(*caps) if caps else self.func(match)
    return result if isinstance(result, tuple) else (result,)

class ReductionCapture(Compound):
  __slots__ = ('func',)

  def __init__(self, member, func):
    super().__init__(member)
    self.func = func

  def _apply(self, state):
    if not (s := self.member._apply(state)):
      return s
    statecaptures = state.captures
    if not statecaptures:
      raise FoxyError('reduction capture with no initial capture(s)')
    acc = statecaptures[-1]
    match = state.string[state.pos:s.pos]
    caps = s.captures[len(statecaptures):]
    result = self.func(acc, *caps) if caps else self.func(acc, match)
    if not isinstance(result, tuple):
      result = (result,)
    return s.succeed(captures=statecaptures[:-1] + result)

class MatchTimeCapture(Compound):
  __slots__ = ('func',)

  def __init__(self, member, func):
    super().__init__(member)
    self.func = func

  def _apply(self, state):
    if not (s := self.member._apply(state)):
      return s
    match = state.string[state.pos:s.pos]
    caps = s.captures[len(state.captures):]
    return self.func(s, match, caps)

Cmt = MatchTimeCapture

### Utils ###

def backref(n):
  return MatchTimeCapture(BackCapture(n), _backref) >> ()

def _backref(s, match, caps):
  return P(caps[0])._apply(s)

def options(*values):
  match values:
    case (dict() as x,): return options(*x) >> x.get
    case (list() as x,): return options(*x)
    case _: return OneOf(*sorted(values, key=len, reverse=True))

def quoted(begin, end=None):
  end = end or begin
  return Regex(rf'{begin}[^\\{end}]*(?:\\.[^\\{end}]*)*{end}')

##### Meta-Grammar ###

def _makemeta():
  def grammar_eval(*items):
    return {items[i]: items[i + 1] for i in range(0, len(items), 2)}

  def regex_eval(string):
    return Regex(_regex.sub(r'\\/', '/', string[1:-1]))

  def const_eval(string):
    return ConstantCapture(_ast.literal_eval(string[1:-1]))

  WS = R(r'[\s--\n]*(?:#.*)?')
  NLWS = R(r'\s*(?:#.*\s*)*')
  NEWLINE = '\n' + NLWS | -1

  return grammar({
    'start': NLWS + (V('grammar') | V('expr')) + -1,
    'grammar': V('rule')**1 >> grammar_eval,
    'rule'
      : V('rulename') + V('expr') + NEWLINE + (V('extra_expr') << _operator.or_)**0
      | V('rulename') + NEWLINE + V('extra_expr') + (V('extra_expr') << _operator.or_)**0,
    'rulename': V('NAME') + WS + ':' + WS,
    'expr': V('seq') + ('|' + WS + V('seq') << _operator.or_)**0,
    'extra_expr': '|' + WS + V('expr') + NEWLINE,
    'seq': V('prefix') + (V('prefix') << _operator.add)**0,
    'prefix'
      : '&' + Cut() + WS + V('suffix') >> _operator.pos
      | '!' + Cut() + WS + V('suffix') >> _operator.neg
      | '~' + WS + Cc(Cut())
      | V('suffix'),
    'suffix': V('atom') + (V('quant') << _operator.pow)**-1,
    'quant'
      : '?' + WS + Cc(-1)
      | '*' + WS + Cc(0)
      | '+' + WS + Cc(1)
      | '^' + WS + V('NUMBER') + WS,
    'atom'
      : '(' + Cut() + WS + V('expr') + ')' + WS
      | '{}' + WS + Cc(PositionCapture())
      | '{:' + Cut() + WS + V('expr') + ':}' + WS >> GroupCapture
      | '{-' + Cut() + WS + V('expr') + '-}' + WS >> ScopeCapture
      | '{' + Cut() + WS + V('expr') + '}' + WS >> SimpleCapture
      | V('STRING') + WS >> Literal
      | V('CLASS') + WS >> Regex
      | V('REGEX') + WS >> regex_eval
      | V('CONST') + WS >> const_eval
      | V('NAME') + WS >> Variable
      | '=' + V('NUMBER') + WS >> backref
      | '.' + WS + Cc(Any()),
    'NAME': C(R(r'[\w--\d]\w*')),
    'NUMBER': R(r'-?\d+') >> _ast.literal_eval,
    'STRING': R(r'r?') + V('STR_BODY') >> _ast.literal_eval,
    'STR_BODY': quoted("'") | quoted('"'),
    'CLASS': C(quoted('\\[', '\\]')),
    'REGEX': C(quoted('/')),
    'CONST': C(quoted('`'))
  })

_meta = _makemeta()

##### Exceptions #####

class FoxyError(Exception): pass
class PatternError(FoxyError): pass
