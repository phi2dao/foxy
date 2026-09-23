r"""A lightweight parsing expression grammar (PEG) library.

This module provides two methods for building PEG parsers: Pattern objects and
regular expression-like foxy expressions. Pattern objects allow integrating
python code and parsing, while foxy expressions are generally simpler to write.

This module is heavily inspired by Lua's lpeg and re modules. Blame them.

This module exports the following operations for building Pattern objects:
  P(string)        Matches 'string' exactly
  P(n)             Matches exactly n characters
  P(-n)            Fails if it would match at least n characters
  P(True)          Always matches and consumes no input
  P(False)         Never matches
  R(string)        Matches the regular expression 'string'
  R[string]        Matches the regular expression '[string]'
  patt1 + patt2    Matches patt1 followed by patt2
  patt1 - patt2    Matches patt1 if it is not patt2
  patt1 | patt2    Matches patt1 or patt2, in that order
  +patt            Matches patt and consumes no input
  -patt            Fails if it would match patt and never consumes input
  patt ** n        Matches at least n repetitions of patt
  patt ** -n       Matches at most n repetitions of patt
  patt ** (m, n)   Matches between m and n repetitions of patt

Recursive Pattern objects can be created with grammars. This module exports the
following operations for building grammars:
  Grammar(dict)    Compiles a dictionary of names to Pattern objects into a
                   single Pattern object, resolving all internal references.
                   Matches the first Pattern object defined in the dictionary
  P(dict)          Alias for Grammar(dict)
  V(string)        Creates a reference to another Pattern object in a grammar.
                   Replaced with the the Pattern object it references when the
                   grammar is compiled

In addition to matching strings, Pattern objects can also capture values for
later use. This module exports the following operations for capturing values:
  C(patt)          Captures the substring of the input matched by patt,
                   followed by all captures of patt
  Cb(n)            Matches P(value) where value is the nth previous capture
  Cg(patt)         Captures all captures of patt as a single tuple
  Cs(patt)         Hides all previous captures from patt
  Cc(value)        Captures 'value' and consumes no input
  Cc(factory=func) Captures the result of calling func and consumes no input
  Cp()             Captures the current position and consumes no input
  patt >> None     Discards all captures of patt
  patt >> n        Captures the nth capture of patt and discards the rest
  patt >> (n, ...) Captures the nth, etc. captures of patt and discards the rest
  patt >> dict     Captures dict[key] where key is the first capture of patt.
                   Captures None if key is not in dict
  patt >> func     Calls func with the captures of patt as its arguments and
                   captures the result(s)
  patt << func     Calls func with the last capture before patt and the
                   captures of patt as its arguments and captures the result(s)
  Cmt(patt, func)  Calls func with the current match state and captures of patt
                   as its arguments. The result becomes the new match state
  P(func)          Alias for Cmt("", func)

Pattern objects have the following methods:
  match            Match the Pattern object against the beginning of a string
  search           Search for the first match of the Pattern object in a string
  findall          Find all matches of the Pattern object in a string

Foxy expressions have the following syntax:
  patt1 | patt2    Matches patt1 or patt2, in that order
  patt1 patt2      Matches patt1 followed by patt2
  & patt           Matches patt and consumes no input
  ! patt           Fails if it would match patt and never consumes input
  patt ?           Optionally matches patt
  patt *           Matches zero or more repetitions of patt
  patt +           Matches one or more repetitions of patt
  patt ^ n         Matches exactly n repetitions of patt
  patt ^ +n        Matches at least n repetitions of patt
  patt ^ -n        Matches at most n repetitions of patt
  name = patt      Defines a name to pattern mapping in a grammar
  name             References a pattern in a grammar
  'string'         Matches 'string' exactly
  "string"         Matches 'string' exactly
  [string]         Matches the regular expression '[string]'
  /string/         Matches the regular expression 'string'
  /string/flags    Matches the regular expression 'string' with flags
  .                Matches any character
  \n               Matches P(value) where value is the nth previous capture
  `value`          Captures 'value' and consumes no input
  {}               Captures the current position and consumes no input
  { patt }         Captures the substring of the input matched by patt,
                   followed by all captures of patt
  {: patt :}       Captures all captures of patt as a single tuple
  {- patt -}       Hides all previous captures from patt

This module exports the following functions for using foxy expressions:
  compile          Compile a foxy expression into a Pattern object
  match            Match a foxy expression against the beginning of a string
  search           Search for the first match of a foxy expression in a string
  findall          Find all matches of a foxy expression in a string
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import reduce, wraps

import regex
regex.DEFAULT_VERSION = regex.V1

##### Symbols #####

__all__ = [
  'Any', 'BackCapture', 'C', 'Capture', 'Cb', 'Cc', 'Cg', 'Cmt', 'Compound',
  'ConstantCapture', 'Cp', 'Cs', 'FunctionCapture', 'Grammar', 'GrammarError',
  'GroupCapture', 'Literal', 'MatchData', 'MatchState', 'MatchTimeCapture',
  'NumberedCapture', 'OneOf', 'Options', 'P', 'Pattern', 'PositionCapture',
  'Predicate', 'QueryCapture', 'Quoted', 'R', 'ReductionCapture', 'Regex',
  'Repetition', 'ScopeCapture', 'Sequence', 'SimpleCapture', 'V', 'Variable',
  'compile', 'findall', 'match', 'search'
]

__version__ = '1.4.0'

##### API #####

def P(value):
  match value:
    case Pattern(): return value
    case str(x): return Literal(x)
    case bool(x): return Any(0) if x else -Any(0)
    case int(x): return Any(x) if x >= 0 else -Any(-x)
    case dict(x): return Grammar(x)
    case x if callable(x): return MatchTimeCapture(Any(0), x)
    case _: raise TypeError(value.__class__.__name__)

# R   = Regex
# V   = Variable
# C   = SimpleCapture
# Cb  = BackCapture
# Cc  = ConstantCapture
# Cp  = PositionCapture
# Cg  = GroupCapture
# Cs  = ScopeCapture
# Cmt = MatchTimeCapture

def compile(pattern):
  if isinstance(pattern, Pattern):
    return pattern
  if m := _foxexp.match(pattern):
    return m.captures[0]

def match(pattern, string, start=0):
  return compile(pattern).match(string, start)

def search(pattern, string, start=0):
  return compile(pattern).search(string, start)

def findall(pattern, string, start=0):
  return compile(pattern).findall(string, start)

### Pattern DSL ###

def _takespattern(func):
  @wraps(func)
  def wrapper(self, other):
    try:
      return func(self, P(other))
    except TypeError:
      return NotImplemented
  return wrapper

class _DSL:
  @_takespattern
  def __add__(self, other):
    smems = self.members if isinstance(self, Sequence) else (self,)
    omems = other.members if isinstance(other, Sequence) else (other,)
    return Sequence(*smems, *omems)

  @_takespattern
  def __sub__(self, other):
    return -other + self

  @_takespattern
  def __or__(self, other):
    smems = self.members if isinstance(self, OneOf) else (self,)
    omems = other.members if isinstance(other, OneOf) else (other,)
    return OneOf(*smems, *omems)

  def __pow__(self, n):
    match n:
      case int(x), int(y): return Repetition(self, x, y)
      case int(x) if x >= 0: return Repetition(self, x, None)
      case int(x): return Repetition(self, 0, -x)
      case _: return NotImplemented

  def __pos__(self):
    match self:
      case Predicate(): return Predicate(self.member, self.polarity)
      case _: return Predicate(self, True)

  def __neg__(self):
    match self:
      case Predicate(): return Predicate(self.member, not self.polarity)
      case _: return Predicate(self, False)

  def __rshift__(self, value):
    match value:
      case None: return NumberedCapture(self, None)
      case int(x) | tuple(x): return NumberedCapture(self, x)
      case dict(x): return QueryCapture(self, x)
      case x if callable(x): return FunctionCapture(self, x)
      case _: return NotImplemented

  def __lshift__(self, value):
    match value:
      case x if callable(x): return ReductionCapture(self, x)
      case _: return NotImplemented

##### Patterns #####

class Pattern(ABC, _DSL):
  __slots__ = ()

  def match(self, string, start=0):
    state = self._apply(MatchState(string, start))
    if state is not None:
      return MatchData(self, string, start, state.pos, state.captures)

  def search(self, string, start=0):
    for pos in range(start, len(string)):
      if m := self.match(string, pos):
        return m

  def findall(self, string, start=0):
    while m := self.search(string, start):
      start = m.end
      yield m

  @abstractmethod
  def _apply(self, state):
    ...

  def _resolve(self, rules):
    return self

@dataclass(frozen=True, slots=True)
class MatchState:
  string: str
  pos: int
  captures: tuple = field(default_factory=tuple)

  def advance(self, pos=None, *, captures=None):
    if pos is None:
      pos = self.pos
    if captures is None:
      captures = self.captures
    return MatchState(self.string, pos, captures)

  def append(self, capture):
    return self.advance(captures=(*self.captures, capture))

  def extend(self, captures):
    return self.advance(captures=self.captures + captures)

@dataclass(frozen=True, slots=True)
class MatchData:
  pattern: Pattern
  string: str
  start: int
  end: int
  captures: tuple = field(default_factory=tuple)

  @property
  def match(self):
    return self.string[self.start:self.end]

  def __getitem__(self, key):
    match key:
      case tuple(): return tuple(self.captures[k] for k in key)
      case _: return self.captures[key]

  def __repr__(self):
    caps = (f' {i}:{c!r}' for i, c in enumerate(self.captures))
    return f'<MatchData {self.match!r}{''.join(caps)}>'

### Atoms ###

class Literal(Pattern):
  __slots__ = ('literal',)

  def __init__(self, literal):
    self.literal = literal

  def _apply(self, state):
    if state.string.startswith(self.literal, state.pos):
      return state.advance(state.pos + len(self.literal))

class Regex(Pattern):
  __slots__ = ('expr',)

  def __class_getitem__(cls, expr):
    return cls(f'[{expr}]')

  def __init__(self, expr, flags=0):
    self.expr = regex.compile(expr, flags)

  def _apply(self, state):
    if m := self.expr.match(state.string, state.pos):
      return state.advance(m.end(), captures=state.captures + m.groups())

R = Regex

class Any(Pattern):
  __slots__ = ('n',)

  def __init__(self, n=1):
    self.n = n

  def _apply(self, state):
    npos = state.pos + self.n
    if npos <= len(state.string):
      return state.advance(npos)

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
      if state is None:
        break
    return state

class OneOf(Compound):
  __slots__ = ()

  def _apply(self, state):
    for m in self.members:
      s = m._apply(state)
      if s is not None:
        return s

class Repetition(Compound):
  __slots__ = ('min', 'max')

  def __init__(self, member, min=0, max=None):
    super().__init__(member)
    self.min = min
    self.max = max

  def _apply(self, state):
    min, max = self.min, self.max
    m, i = self.member, 0
    while max is None or i < max:
      s = m._apply(state)
      if s is None:
        break
      i += 1
      if s.pos == state.pos and i > min:
        break
      state = s
    if i >= min:
      return state

class Predicate(Compound):
  __slots__ = ('polarity',)

  def __init__(self, member, polarity):
    super().__init__(member)
    self.polarity = polarity

  def _apply(self, state):
    s = self.member._apply(state)
    if (s is not None) == self.polarity:
      return state

### Grammar ###

def Grammar(rules):
  if not rules:
    raise ValueError("can't compile grammar without rules")
  for name, patt in rules.items():
    rules[name] = patt._resolve(rules)
  return next(iter(rules.values()))

class Variable(Pattern):
  __slots__ = ('name',)

  def __init__(self, name):
    self.name = name

  def _apply(self, state):
    raise GrammarError(f'unresolved reference {self.name!r}')

  def _resolve(self, rules):
    seen, cur = set(), self
    while isinstance(cur, Variable):
      if cur in seen:
        raise GrammarError(f'circular reference resolving {self.name!r}')
      seen.add(cur)
      try:
        cur = rules[cur.name]
      except KeyError:
        raise GrammarError(f'rule {cur.name!r} is not defined')
    return cur

V = Variable

class GrammarError(Exception):
  pass

### Captures ###

class Capture(Compound):
  __slots__ = ()

  def __init__(self, member):
    super().__init__(member)

  def _apply(self, state):
    if s := self.member._apply(state):
      i, c = len(state.captures), s.captures
      match = state.string[state.pos:s.pos]
      return s.advance(captures=self._capture(match, c[:i], c[i:]))

  @abstractmethod
  def _capture(self, match, head, rest):
    ...

class SimpleCapture(Capture):
  __slots__ = ()

  def _capture(self, match, head, rest):
    return (*head, match, *rest)

C = SimpleCapture

class BackCapture(Pattern):
  __slots__ = ('n',)

  def __init__(self, n):
    self.n = n

  def _apply(self, state):
    return P(state.captures[self.n])._apply(state)

Cb = BackCapture

_MISSING = object()

class ConstantCapture(Pattern):
  __slots__ = ('const', 'factory')

  def __init__(self, const=_MISSING, *, factory=_MISSING):
    if const is not _MISSING and factory is not _MISSING:
      raise ValueError('cannot specify both const and factory')
    self.const = const
    self.factory = factory

  def _apply(self, state):
    return state.append(self.const if self.factory is _MISSING else self.factory())

Cc = ConstantCapture

class PositionCapture(Pattern):
  __slots__ = ()

  def _apply(self, state):
    return state.append(state.pos)

Cp = PositionCapture

class GroupCapture(Capture):
  __slots__ = ()

  def _capture(self, match, head, rest):
    return (*head, rest)

Cg = GroupCapture

class ScopeCapture(Compound):
  __slots__ = ()

  def __init__(self, member):
    super().__init__(member)

  def _apply(self, state):
    if s := self.member._apply(state.advance(captures=())):
      return s.advance(captures=state.captures + s.captures)

Cs = ScopeCapture

class NumberedCapture(Capture):
  __slots__ = ('n',)

  def __init__(self, member, n):
    super().__init__(member)
    self.n = n

  def _capture(self, match, head, rest):
    match self.n:
      case None: return head
      case int(x): return (*head, rest[x])
      case tuple(x): return (*head, *(rest[n] for n in x))

class QueryCapture(Capture):
  __slots__ = ('lookup',)

  def __init__(self, member, lookup):
    super().__init__(member)
    self.lookup = lookup

  def _capture(self, match, head, rest):
    key = rest[0] if rest else match
    return (*head, self.lookup.get(key))

class FunctionCapture(Capture):
  __slots__ = ('func',)

  def __init__(self, member, func):
    super().__init__(member)
    self.func = func

  def _capture(self, match, head, rest):
    caps = self.func(*rest) if rest else self.func(match)
    return head + caps if isinstance(caps, tuple) else (*head, caps)

class ReductionCapture(Capture):
  __slots__ = ('func',)

  def __init__(self, member, func):
    super().__init__(member)
    self.func = func

  def _capture(self, match, head, rest):
    caps = self.func(head[-1], *rest) if rest else self.func(head[-1], match)
    return head[:-1] + caps if isinstance(caps, tuple) else (*head[:-1], caps)

class MatchTimeCapture(Compound):
  __slots__ = ('func',)

  def __init__(self, member, func):
    super().__init__(member)
    self.func = func

  def _apply(self, state):
    if s := self.member._apply(state):
      i, c = len(state.captures), s.captures
      return self.func(s, c[:i], c[i:])

Cmt = MatchTimeCapture

### Convenience ###

def Options(*options, optiondict=None):
  if options and optiondict:
    raise ValueError('cannot specify both options and optiondict')
  pattern = OneOf(*sorted(optiondict or options, key=len, reverse=True))
  return pattern >> optiondict if optiondict else pattern

def Quoted(begin, end=None):
  begin, end = regex.escape(begin), regex.escape(end or begin)
  return Regex(rf'{begin}[^\\{end}]*(?:\\.[^\\{end}]*)*{end}')

##### FoxyExpressions #####

from ast import literal_eval

def _regex_eval(string, flags):
  expr = regex.sub(r'\\/', '/', string[1:-1])
  flags = reduce(lambda x, y: x | regex.RegexFlag[y.upper()], flags, 0)
  return Regex(expr, flags)

def _const_eval(string):
  return ConstantCapture(literal_eval(string[1:-1]))

def _grammar_eval(*items):
  return Grammar({items[i]: items[i + 1] for i in range(0, len(items), 2)})

_foxexp = Grammar({
  'pattern': V('WS') + V('exp') + P(-1),
  'exp': V('grammar') | V('one_of'),
  'one_of': V('sequence') + (V('OR') + V('sequence') << OneOf)**0,
  'sequence': V('prefix') + (V('prefix') << Sequence)**0,
  'prefix': V('AND') + V('prefix') + Cc(True) >> Predicate
          | V('NOT') + V('prefix') + Cc(False) >> Predicate
          | V('suffix'),
  'suffix': V('primary') + (V('repetition') << Repetition)**0,
  'repetition': V('QMARK') + Cc(0) + Cc(1)
          | V('STAR') + Cc(0) + Cc(None)
          | V('PLUS') + Cc(1) + Cc(None)
          | V('CARET') + P('+') + V('num') + Cc(None)
          | V('CARET') + P('-') + Cc(0) + V('num')
          | V('CARET') + V('num') >> (0, 0),
  'primary': V('name') + -V('EQUALS') >> Variable
          | V('string') >> literal_eval >> Literal
          | V('class') >> Regex
          | V('regex') >> _regex_eval
          | V('const') >> _const_eval
          | P('\\') + V('num') >> BackCapture
          | P('.') + V('WS') + Cc(Any())
          | P('{}') + V('WS') + Cc(Cp())
          | V('OPEN') + V('exp') + V('CLOSE')
          | V('COPEN') + V('exp') + V('CCLOSE') >> SimpleCapture
          | V('GOPEN') + V('exp') + V('GCLOSE') >> GroupCapture
          | V('SOPEN') + V('exp') + V('SCLOSE') >> ScopeCapture,
  'grammar': V('definition')**1 >> _grammar_eval,
  'definition': V('name') + V('EQUALS') + V('exp'),
  'name': C(R(r'[\w--\d]\w*')) + V('WS'),
  'string': C(Quoted("'") | Quoted('"')) + V('WS'),
  'class': C(Quoted('[', ']')) + V('WS'),
  'regex': C(Quoted('/')) + C(R(r'(?i)[a-z]*')) + V('WS'),
  'const': C(Quoted('`')) + V('WS'),
  'num': C(R(r'[+-]?\d+')) + V('WS') >> literal_eval,
  'WS': R(r'(?:\s+|#[^\n]*)*'),
  'OR': P('|') + V('WS'),
  'AND': P('&') + V('WS'),
  'NOT': P('!') + V('WS'),
  'QMARK': P('?') + V('WS'),
  'STAR': P('*') + V('WS'),
  'PLUS': P('+') + V('WS'),
  'CARET': P('^') + V('WS'),
  'EQUALS': P('=') + V('WS'),
  'OPEN': P('(') + V('WS'),
  'CLOSE': P(')') + V('WS'),
  'COPEN': P('{') + V('WS'),
  'CCLOSE': P('}') + V('WS'),
  'GOPEN': P('{:') + V('WS'),
  'GCLOSE': P(':}') + V('WS'),
  'SOPEN': P('{-') + V('WS'),
  'SCLOSE': P('-}') + V('WS')
})
