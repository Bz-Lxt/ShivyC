"""Type operation expression nodes in the AST."""

import shivyc.ctypes as ctypes
from shivyc.errors import CompilerError
from shivyc.il_gen import ILValue
from shivyc.tree.expr_base import _RExprNode
from shivyc.tree.general_nodes import Declaration
from shivyc.tree.utils import set_type, sizeof_ctype as runtime_sizeof


class _SizeofNode(_RExprNode):
    """Base class for common logic for the two sizeof nodes."""

    def __init__(self):
        super().__init__()

    def sizeof_ctype(self, ctype, range, il_code, symbol_table, c):
        """Return IL code for the size of the given type.

        Raises CompilerError if ctype is not valid as a sizeof argument.
        For a variable length array type the resulting size is a runtime
        value, and the bound expressions are evaluated.
        """

        if ctype.is_function():
            err = "sizeof argument cannot have function type"
            raise CompilerError(err, range)

        if ctype.is_incomplete():
            err = "sizeof argument cannot have incomplete type"
            raise CompilerError(err, range)

        return runtime_sizeof(ctype, il_code, symbol_table, c)


class SizeofExpr(_SizeofNode):
    """Node representing sizeof with expression operand.

    expr (_ExprNode) - the expression to get the size of
    """
    def __init__(self, expr):
        super().__init__()
        self.expr = expr

    def make_il(self, il_code, symbol_table, c):
        """Make IL for this sizeof expression.

        Normally the operand expression is not evaluated, but if its type
        is a variable length array type the size is a runtime value (the
        bound itself was evaluated when the array was declared).
        """

        dummy_il_code = il_code.copy()
        dummy_il_code.vla_dry_run = True
        expr = self.expr.make_il_raw(dummy_il_code, symbol_table, c)
        return self.sizeof_ctype(
            expr.ctype, self.expr.r, il_code, symbol_table, c)


class SizeofType(_SizeofNode, Declaration):
    """Node representing sizeof with abstract type as operand.

    node (decl_nodes.Root) - a declaration tree for the type
    """
    def __init__(self, node):
        _SizeofNode.__init__(self)
        Declaration.__init__(self, node)   # sets self.node = node

    def make_il(self, il_code, symbol_table, c):
        """Make IL for this sizeof expression.

        If the type is a variable length array type, the size expression is
        evaluated at runtime.
        """

        self.set_self_vars(il_code, symbol_table, c)
        base_type, _ = self.make_specs_ctype(self.node.specs, False)
        ctype, _ = self.make_ctype(self.node.decls[0], base_type)
        return self.sizeof_ctype(
            ctype, self.node.decls[0].r, il_code, symbol_table, c)


class Cast(Declaration, _RExprNode):
    """Node representing a cast operation, like `(void*)p`.

    node (decl_nodes.Root) - a declaration tree for this line

    TODO: Share code between Cast and Declaration nodes more cleanly.
    """
    def __init__(self, node, expr):
        Declaration.__init__(self, node)   # sets self.node = node
        _RExprNode.__init__(self)

        self.expr = expr

    def make_il(self, il_code, symbol_table, c):
        """Make IL for this cast operation."""

        self.set_self_vars(il_code, symbol_table, c)
        base_type, _ = self.make_specs_ctype(self.node.specs, False)
        ctype, _ = self.make_ctype(self.node.decls[0], base_type)

        if not ctype.is_void() and not ctype.is_scalar():
            err = "can only cast to scalar or void type"
            raise CompilerError(err, self.node.decls[0].r)

        il_value = self.expr.make_il(il_code, symbol_table, c)
        if not il_value.ctype.is_scalar():
            err = "can only cast from scalar type"
            raise CompilerError(err, self.r)

        return set_type(il_value, ctype, il_code)
