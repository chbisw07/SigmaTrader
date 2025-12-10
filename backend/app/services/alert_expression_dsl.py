from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.services.alert_expression import (
    ComparisonNode,
    ExpressionNode,
    FieldOperand,
    IndicatorOperand,
    IndicatorSpec,
    LogicalNode,
    NotNode,
    NumberOperand,
)
from app.services.indicator_alerts import IndicatorAlertError
from app.services.market_data import Timeframe


@dataclass
class _Token:
    kind: str
    value: str


def _tokenize(expr: str) -> List[_Token]:
    import re

    tokens: List[_Token] = []
    pattern = re.compile(
        r"\s+|"
        r"(?P<NUMBER>\d+(\.\d+)?)|"
        r"(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)|"
        r"(?P<OP>==|!=|>=|<=|>|<)|"
        r"(?P<LPAREN>\()|"
        r"(?P<RPAREN>\))|"
        r"(?P<COMMA>,)"
    )
    for match in pattern.finditer(expr):
        if match.group(0).isspace():
            continue
        for kind in ("NUMBER", "IDENT", "OP", "LPAREN", "RPAREN", "COMMA"):
            val = match.group(kind)
            if val is not None:
                tokens.append(_Token(kind, val))
                break
    return tokens


# Supported timeframes for indicators; must stay in sync with
# app.services.market_data.Timeframe.
_ALLOWED_TIMEFRAMES = {
    "1m",
    "5m",
    "15m",
    "1h",
    "1d",
    "1mo",
    "1y",
}

_ALLOWED_FIELDS = {
    "INVESTED",
    "PNL_PCT",
    "QTY",
    "AVG_PRICE",
    "CURRENT_VALUE",
}

# Supported indicators for the DSL; these should mirror
# app.schemas.indicator_rules.IndicatorType and the implementations in
# app.services.indicator_alerts._compute_indicator_sample.
_ALLOWED_INDICATORS = {
    "PRICE",
    "RSI",
    "MA",
    "MA_CROSS",
    "VOLATILITY",
    "ATR",
    "PERF_PCT",
    "VOLUME_RATIO",
    "VWAP",
    "PVT",
    "PVT_SLOPE",
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
            raise IndicatorAlertError(
                f"Expected '{value}' but found '{tok.value}'",
            )
        self.pos += 1
        return tok

    def parse(self) -> ExpressionNode:
        expr = self._parse_or()
        if self._peek() is not None:
            raise IndicatorAlertError(
                f"Unexpected token '{self._peek().value}' at end of expression",  # type: ignore[union-attr]
            )
        return expr

    # Grammar (simplified):
    # expr_or    := expr_and (OR expr_and)*
    # expr_and   := expr_not (AND expr_not)*
    # expr_not   := NOT expr_not | expr_cmp
    # expr_cmp   := sum_expr (COMPARISON_OP sum_expr)?
    # sum_expr   := primary

    def _parse_or(self) -> ExpressionNode:
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

    def _parse_and(self) -> ExpressionNode:
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

    def _parse_not(self) -> ExpressionNode:
        tok = self._peek()
        if tok and tok.kind == "IDENT" and tok.value.upper() == "NOT":
            self._consume("IDENT")
            child = self._parse_not()
            return NotNode(child)
        return self._parse_comparison()

    def _parse_comparison(self) -> ExpressionNode:
        left = self._parse_primary()
        tok = self._peek()
        if tok is None:
            return left

        # Long-form operators like CROSS_ABOVE / CROSS_BELOW
        if tok.kind == "IDENT":
            op_ident = tok.value.upper()
            if op_ident in {"CROSS_ABOVE", "CROSS_BELOW"}:
                self._consume("IDENT")
                right = self._parse_primary()
                return ComparisonNode(left, op_ident, right)

        # Symbolic operators: >, >=, <, <=, ==, !=
        if tok.kind == "OP":
            op_map = {
                ">": "GT",
                ">=": "GTE",
                "<": "LT",
                "<=": "LTE",
                "==": "EQ",
                "!=": "NEQ",
            }
            op_val = op_map.get(tok.value)
            if op_val is None:
                raise IndicatorAlertError(
                    f"Unsupported comparison operator '{tok.value}'",
                )
            self._consume("OP")
            right = self._parse_primary()
            return ComparisonNode(left, op_val, right)

        return left

    def _parse_primary(self) -> ExpressionNode | NumberOperand | IndicatorOperand:
        tok = self._peek()
        if tok is None:
            raise IndicatorAlertError("Unexpected end of expression")

        if tok.kind == "NUMBER":
            self._consume("NUMBER")
            return NumberOperand(float(tok.value))

        if tok.kind == "LPAREN":
            self._consume("LPAREN")
            expr = self._parse_or()
            self._consume("RPAREN")
            return expr

        if tok.kind == "IDENT":
            ident = self._consume("IDENT").value
            next_tok = self._peek()

            # Field reference when there is no '(' after the identifier.
            if not next_tok or next_tok.kind != "LPAREN":
                name = ident.upper()
                if name not in _ALLOWED_FIELDS:
                    raise IndicatorAlertError(f"Unknown field '{name}'")
                return FieldOperand(name)

            # Indicator call: IDENT '(' args ')'
            ident_upper = ident.upper()
            if ident_upper not in _ALLOWED_INDICATORS:
                raise IndicatorAlertError(f"Unknown indicator '{ident_upper}'")
            self._consume("LPAREN")
            timeframe: Timeframe = "1d"
            params: dict[str, object] = {}

            # Parse arguments. We support:
            # - INDICATOR(14, 1D)
            # - INDICATOR(14)
            # - INDICATOR(1D)
            first = self._peek()
            second = (
                self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            )

            # Case: timeframe encoded as NUMBER + IDENT, e.g. 1d, 15m
            if first and first.kind == "NUMBER" and second and second.kind == "IDENT":
                candidate = (first.value + second.value).lower()
                if candidate in _ALLOWED_TIMEFRAMES:
                    self._consume("NUMBER")
                    self._consume("IDENT")
                    timeframe = candidate  # type: ignore[assignment]
                else:
                    # Treat as period followed by optional comma.
                    period_tok = self._consume("NUMBER")
                    period = int(float(period_tok.value))
                    params["period"] = period
                    if self._peek() and self._peek().kind == "COMMA":
                        self._consume("COMMA")
            elif first and first.kind == "NUMBER":
                period_tok = self._consume("NUMBER")
                period = int(float(period_tok.value))
                params["period"] = period
                if self._peek() and self._peek().kind == "COMMA":
                    self._consume("COMMA")

            if self._peek() and self._peek().kind == "IDENT":
                tf_tok = self._consume("IDENT")
                tf_val = tf_tok.value.lower()
                if tf_val in _ALLOWED_TIMEFRAMES:
                    timeframe = tf_val  # type: ignore[assignment]
                else:
                    raise IndicatorAlertError(f"Unsupported timeframe '{tf_tok.value}'")

            # Consume remaining until ')'
            while self._peek() and self._peek().kind != "RPAREN":
                self._consume()
            self._consume("RPAREN")

            spec = IndicatorSpec(
                kind=ident_upper,  # type: ignore[arg-type]
                timeframe=timeframe,
                params=params,
            )
            return IndicatorOperand(spec)

        raise IndicatorAlertError(
            f"Unexpected token '{tok.value}' in expression",  # type: ignore[union-attr]
        )


def parse_expression(text: str) -> ExpressionNode:
    parser = _Parser(text)
    return parser.parse()


__all__ = ["parse_expression"]
