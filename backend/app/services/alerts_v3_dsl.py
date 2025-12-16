from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.services.alerts_v3_expression import (
    BinaryNode,
    CallNode,
    ComparisonNode,
    EventNode,
    ExprNode,
    IdentNode,
    LogicalNode,
    NotNode,
    NumberNode,
    UnaryNode,
)
from app.services.indicator_alerts import IndicatorAlertError


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str


def _tokenize(expr: str) -> List[_Token]:
    import re

    # Order matters: timeframe literals like 1h/1d must be captured before NUMBER.
    pattern = re.compile(
        r"\s+|"
        r"(?P<TF>\d+(?:m|h|d|w|mo|y))|"
        r"(?P<NUMBER>\d+(\.\d+)?)|"
        r"(?P<STRING>\"[^\"]*\"|'[^']*')|"
        r"(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)|"
        r"(?P<OP>==|!=|>=|<=|\+|-|\*|/|>|<)|"
        r"(?P<LPAREN>\()|"
        r"(?P<RPAREN>\))|"
        r"(?P<COMMA>,)"
    )
    tokens: List[_Token] = []
    for match in pattern.finditer(expr):
        raw = match.group(0)
        if raw.isspace():
            continue
        for kind in (
            "TF",
            "NUMBER",
            "STRING",
            "IDENT",
            "OP",
            "LPAREN",
            "RPAREN",
            "COMMA",
        ):
            val = match.group(kind)
            if val is not None:
                tokens.append(_Token(kind, val))
                break
    return tokens


_CMP_OP_MAP = {
    ">": "GT",
    ">=": "GTE",
    "<": "LT",
    "<=": "LTE",
    "==": "EQ",
    "!=": "NEQ",
}

_EVENT_OPS = {
    "CROSSES_ABOVE",
    "CROSSES_BELOW",
    "MOVING_UP",
    "MOVING_DOWN",
    # Aliases accepted in user input, canonicalized at parse time.
    "CROSSING_ABOVE",
    "CROSSING_BELOW",
}


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _tokenize(text)
        self.pos = 0

    def _peek(self) -> Optional[_Token]:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def _consume(self, kind: str | None = None, value: str | None = None) -> _Token:
        tok = self._peek()
        if tok is None:
            raise IndicatorAlertError("Unexpected end of expression")
        if kind is not None and tok.kind != kind:
            raise IndicatorAlertError(f"Expected {kind} but found {tok.kind}")
        if value is not None and tok.value.upper() != value.upper():
            raise IndicatorAlertError(f"Expected '{value}' but found '{tok.value}'")
        self.pos += 1
        return tok

    def parse(self) -> ExprNode:
        expr = self._parse_or()
        if self._peek() is not None:
            raise IndicatorAlertError(
                f"Unexpected token '{self._peek().value}' at end of expression"  # type: ignore[union-attr]
            )
        return expr

    # Grammar (as per docs/alerts_refactor_v3.md):
    # or     := and ('OR' and)*
    # and    := not ('AND' not)*
    # not    := 'NOT' not | cmp
    # cmp    := add ( (EVENT_OP add) | (CMP_OP add) )?
    # add    := mul (('+'|'-') mul)*
    # mul    := unary (('*'|'/') unary)*
    # unary  := ('+'|'-') unary | primary
    # primary:= NUMBER | IDENT | TF | STRING | call | '(' or ')'

    def _parse_or(self) -> ExprNode:
        node = self._parse_and()
        children = [node]
        while True:
            tok = self._peek()
            if tok and tok.kind == "IDENT" and tok.value.upper() == "OR":
                self._consume("IDENT")
                children.append(self._parse_and())
            else:
                break
        if len(children) == 1:
            return node
        return LogicalNode("OR", children)

    def _parse_and(self) -> ExprNode:
        node = self._parse_not()
        children = [node]
        while True:
            tok = self._peek()
            if tok and tok.kind == "IDENT" and tok.value.upper() == "AND":
                self._consume("IDENT")
                children.append(self._parse_not())
            else:
                break
        if len(children) == 1:
            return node
        return LogicalNode("AND", children)

    def _parse_not(self) -> ExprNode:
        tok = self._peek()
        if tok and tok.kind == "IDENT" and tok.value.upper() == "NOT":
            self._consume("IDENT")
            return NotNode(self._parse_not())
        return self._parse_cmp()

    def _parse_cmp(self) -> ExprNode:
        left = self._parse_add()
        tok = self._peek()
        if tok is None:
            return left

        # Event operators (as IDENT)
        if tok.kind == "IDENT":
            op = tok.value.upper()
            if op in _EVENT_OPS:
                self._consume("IDENT")
                right = self._parse_add()
                canonical = {
                    "CROSSING_ABOVE": "CROSSES_ABOVE",
                    "CROSSING_BELOW": "CROSSES_BELOW",
                }.get(op, op)
                return EventNode(canonical, left, right)

        # Symbolic comparison operators
        if tok.kind == "OP" and tok.value in _CMP_OP_MAP:
            op = _CMP_OP_MAP[tok.value]
            self._consume("OP")
            right = self._parse_add()
            return ComparisonNode(op, left, right)

        return left

    def _parse_add(self) -> ExprNode:
        node = self._parse_mul()
        while True:
            tok = self._peek()
            if tok and tok.kind == "OP" and tok.value in {"+", "-"}:
                op = tok.value
                self._consume("OP")
                right = self._parse_mul()
                node = BinaryNode(op, node, right)
            else:
                break
        return node

    def _parse_mul(self) -> ExprNode:
        node = self._parse_unary()
        while True:
            tok = self._peek()
            if tok and tok.kind == "OP" and tok.value in {"*", "/"}:
                op = tok.value
                self._consume("OP")
                right = self._parse_unary()
                node = BinaryNode(op, node, right)
            else:
                break
        return node

    def _parse_unary(self) -> ExprNode:
        tok = self._peek()
        if tok and tok.kind == "OP" and tok.value in {"+", "-"}:
            op = tok.value
            self._consume("OP")
            return UnaryNode(op, self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> ExprNode:
        tok = self._peek()
        if tok is None:
            raise IndicatorAlertError("Unexpected end of expression")

        if tok.kind == "NUMBER":
            self._consume("NUMBER")
            return NumberNode(float(tok.value))

        if tok.kind == "LPAREN":
            self._consume("LPAREN")
            expr = self._parse_or()
            self._consume("RPAREN")
            return expr

        if tok.kind in {"TF", "STRING"}:
            self._consume(tok.kind)
            return IdentNode(tok.value.strip())

        if tok.kind == "IDENT":
            ident = self._consume("IDENT").value
            nxt = self._peek()
            if not nxt or nxt.kind != "LPAREN":
                return IdentNode(ident)

            # Function call: IDENT '(' args ')'
            self._consume("LPAREN")
            args: List[ExprNode] = []
            if self._peek() and self._peek().kind != "RPAREN":
                while True:
                    args.append(self._parse_or())
                    if self._peek() and self._peek().kind == "COMMA":
                        self._consume("COMMA")
                        continue
                    break
            self._consume("RPAREN")
            return CallNode(ident, args)

        raise IndicatorAlertError(f"Unexpected token '{tok.value}'")


def parse_v3_expression(expr: str) -> ExprNode:
    """Parse a v3 alert DSL expression into the v3 AST.

    This parser is used for both alert conditions and custom indicator bodies.
    Additional semantic validation (numeric-only constraints, allowed functions,
    etc.) is performed in the compilation layer.
    """

    return _Parser(expr).parse()


__all__ = ["parse_v3_expression"]
