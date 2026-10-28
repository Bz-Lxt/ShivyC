"""Utility objects for the AST nodes and IL generation steps of ShivyC."""

from contextlib import contextmanager

import shivyc.ctypes as ctypes
import shivyc.il_cmds.value as value_cmds
import shivyc.il_cmds.math as math_cmds

from shivyc.ctypes import PointerCType
from shivyc.errors import CompilerError, error_collector
from shivyc.il_gen import ILValue


class LValue:
    """Represents an LValue."""

    def ctype(self):
        """Return the ctype that is stored by this LValue.

        For example, if this LValue represents a dereferenced pointer to an
        integer, then this function returns a ctype of integer.
        """
        raise NotImplementedError

    def set_to(self, rvalue, il_code, r):
        """Emit code to set the given lvalue to the given ILValue.

        rvalue (ILValue) - rvalue to set this lvalue to
        il_code (ILCode) - ILCode object to add generated code
        r (Range) - Range for warning/error messages
        return - ILValue representing the result of this operation

        """
        raise NotImplementedError

    def addr(self, il_code):
        """Generate code for and return address of this lvalue."""
        raise NotImplementedError

    def val(self, il_code):
        """Generate code for and return the value currently stored."""
        raise NotImplementedError

    def modable(self):
        """Return whether this is a modifiable lvalue."""

        # TODO: add "is not const qualified" and "if struct/union, has no
        # const qualified member"
        ctype = self.ctype()
        if ctype.is_array():
            return False
        if ctype.is_incomplete():
            return False
        if ctype.is_const():
            return False
        if (ctype.is_struct_union()
             and any(m[1].is_const() for m in ctype.members)):
            return False

        return True


class DirectLValue(LValue):
    """Represents a direct LValue.

    A direct LValue stores an ILValue to which this LValue refers. For
    example, a variable is a direct LValue.
    """
    def __init__(self, il_value):
        """Initialize DirectLValue with the IL value it represents."""
        self.il_value = il_value

    def ctype(self):  # noqa D102
        return self.il_value.ctype

    def set_to(self, rvalue, il_code, r):  # noqa D102
        check_cast(rvalue, self.ctype(), r)
        return set_type(rvalue, self.ctype(), il_code, self.il_value)

    def addr(self, il_code):  # noqa D102
        out = ILValue(PointerCType(self.il_value.ctype))
        il_code.add(value_cmds.AddrOf(out, self.il_value))
        return out

    def val(self, il_code):  # noqa D102
        return self.il_value


class IndirectLValue(LValue):
    """Represents an indirect LValue.

    An indirect LValue stores an ILValue which is the address of the object
    represented by this LValue. For example, a dereferenced pointer or an
    array subscripted value is an IndirectLValue.
    """
    def __init__(self, addr_val):
        """Initialize the IndirectLValue.

        addr_val must be an ILValue containing the address of the object
        pointed to by this LValue.
        """
        self.addr_val = addr_val

    def ctype(self):  # noqa D102
        return self.addr_val.ctype.arg

    def set_to(self, rvalue, il_code, r):  # noqa D102
        check_cast(rvalue, self.ctype(), r)
        right_cast = set_type(rvalue, self.ctype(), il_code)
        il_code.add(value_cmds.SetAt(self.addr_val, right_cast))
        return right_cast

    def addr(self, il_code):  # noqa D102
        return self.addr_val

    def val(self, il_code):  # noqa D102
        out = ILValue(self.ctype())
        il_code.add(value_cmds.ReadAt(out, self.addr_val))
        return out


class RelativeLValue(LValue):
    """Represents a relative LValue.

    A relative LValue is used to represent an LValue that is located in
    memory relative to the position of another ILValue. For example,
    in the expression `array[5] = 3`, the `array[5]` is a RelativeLValue
    because it represents a value offset by 5 from the ILValue of array.

    ctype - The ctype that can be stored in this RelativeLValue. In the
    example above, this would be the integer ctype.

    base - ILValue representing the base object. Note this is the base
    object itself, not the address of the base object.

    chunk - A Python integer representing the size of each chunk of offset.

    count - If provided, an integral ILValue representing the number of
    chunks of offset.

    In summary, if `count` is provided, then the address of the object
    represented by this LValue is:

        &base + chunk * count

    and if `count` is not provided, the address is just

        &base + chunk

    """
    def __init__(self, ctype, base, chunk=0, count=None):
        self._ctype = ctype
        self.base = base
        self.chunk = chunk
        self.count = count

        self.fixed_count = None
        self.fixed_chunk = None

    def _fix_chunk_count(self, il_code):
        """Convert chunk and count so that chunk is in {1, 2, 4, 8}.

        The Rel commands requre that chunk be in {1, 2, 4, 8}. If the
        given chunk value is not in this set, we multiply count and divide
        chunk by an appropriate value so that chunk is in {1, 2, 4, 8},
        and then return the new value of chunk and the new value of count.

        In addition, this command moves `count` to a 64-bit value.
        """
        # Cache the value of fixed_chunk and fixed_count so it is not
        # recomputed unnecessarily
        if self.fixed_chunk or self.fixed_count:
            return

        if not self.count:
            self.fixed_chunk, self.fixed_count = self.chunk, self.count
            return

        # TODO: Technically, if count is an unsigned long and `chunk` is in
        # `sizes`, we don't need to emit a SET command.
        resized_count = set_type(self.count, ctypes.longint, il_code)

        sizes = [8, 4, 2, 1]
        if self.chunk in sizes:
            self.fixed_chunk, self.fixed_count = self.chunk, resized_count
            return

        # Select the biggest legal size that divides given chunk size
        for new_chunk in sizes:
            if self.chunk % new_chunk == 0:
                break

        self.fixed_chunk = new_chunk

        scale = ILValue(ctypes.longint)
        scale_factor = str(int(self.chunk / new_chunk))
        il_code.register_literal_var(scale, scale_factor)

        self.fixed_count = ILValue(ctypes.longint)
        il_code.add(math_cmds.Mult(self.fixed_count, resized_count, scale))

    def ctype(self):
        return self._ctype

    def set_to(self, rvalue, il_code, r):
        self._fix_chunk_count(il_code)
        check_cast(rvalue, self.ctype(), r)
        right_cast = set_type(rvalue, self.ctype(), il_code)
        il_code.add(value_cmds.SetRel(
            right_cast, self.base, self.fixed_chunk, self.fixed_count))
        return right_cast

    def addr(self, il_code):
        self._fix_chunk_count(il_code)
        out = ILValue(PointerCType(self.ctype()))
        il_code.add(value_cmds.AddrRel(
            out, self.base, self.fixed_chunk, self.fixed_count))
        return out

    def val(self, il_code):
        self._fix_chunk_count(il_code)
        out = ILValue(self.ctype())
        il_code.add(value_cmds.ReadRel(
            out, self.base, self.fixed_chunk, self.fixed_count))
        return out


# Mapping from storage unit size, in bytes, to the unsigned integer
# ctype of that size.
_UNSIGNED_UNIT_CTYPES = {1: ctypes.unsig_char,
                         2: ctypes.unsig_short,
                         4: ctypes.unsig_int,
                         8: ctypes.unsig_longint}


class BitFieldLValue(LValue):
    """Represents a bit-field within a struct or union.

    This wraps an LValue for the bit-field's whole allocation unit (an
    unsigned integer ILValue of 1, 2, 4, or 8 bytes), and performs the
    extraction, sign-extension, and read-modify-write logic needed to
    access just the bits of the field.

    storage - LValue for the whole allocation unit holding this field
    field_ctype - declared ctype of this bit-field (may be const)
    bit_pos - position of this field, in bits, within its allocation unit
    bit_width - width of this field in bits
    r - Range of the expression, for error reporting

    """
    def __init__(self, storage, field_ctype, bit_pos, bit_width, r=None):
        """Initialize this bit-field lvalue."""
        self.storage = storage
        self._ctype = field_ctype
        self.bit_pos = bit_pos
        self.bit_width = bit_width
        self.r = r

    def ctype(self):  # noqa D102
        return self._ctype

    def addr(self, il_code):  # noqa D102
        err = "cannot take address of bit-field"
        raise CompilerError(err, self.r)

    def _work_types(self):
        """Return ctypes used to manipulate this field.

        Returns a tuple of the unsigned storage unit ctype, the signed
        working ctype (at least 32 bits wide), and the width, in bits, of
        the working ctype.
        """
        unit_size = self.storage.ctype().size
        unit_unsigned = _UNSIGNED_UNIT_CTYPES[unit_size]
        if unit_size == 8:
            return unit_unsigned, ctypes.longint, 64
        else:
            return unit_unsigned, ctypes.integer, 32

    def _literal(self, il_code, value, ctype):
        """Register an integer literal ILValue of given ctype."""
        lit = ILValue(ctype)
        il_code.register_literal_var(lit, value)
        return lit

    def _shift(self, il_code, output, value, amount, left):
        """Emit a shift of value by a compile-time constant amount."""
        amount_il = self._literal(il_code, amount, value.ctype)
        if left:
            command = math_cmds.LBitShift
        else:
            command = math_cmds.RBitShift
        il_code.add(command(output, value, amount_il))

    def val(self, il_code):  # noqa D102
        unit_unsigned, work_signed, work_bits = self._work_types()
        width = self.bit_width
        pos = self.bit_pos

        # Read the whole allocation unit and widen it, zero-extended, into
        # the working register.
        raw = self.storage.val(il_code)
        work = set_type(raw, work_signed, il_code)

        # Shift the field bits to the bottom of the register and mask off
        # everything else. The right shift is arithmetic, but the mask
        # removes any bits shifted in from the top.
        shifted = ILValue(work_signed)
        self._shift(il_code, shifted, work, pos, False)

        mask = (1 << width) - 1
        masked = ILValue(work_signed)
        il_code.add(math_cmds.And(
            masked, shifted, self._literal(il_code, mask, work_signed)))

        # Sign-extend a signed field from its own width to the full width
        # of the working register using a left shift followed by an
        # arithmetic right shift.
        if self._ctype.signed:
            left = ILValue(work_signed)
            self._shift(il_code, left, masked, work_bits - width, True)
            extended = ILValue(work_signed)
            self._shift(il_code, extended, left, work_bits - width, False)
            value = extended
        else:
            value = masked

        out = ILValue(self._ctype.make_unqual())
        set_type(value, out.ctype, il_code, out)
        return out

    def set_to(self, rvalue, il_code, r):  # noqa D102
        unit_unsigned, work_signed, work_bits = self._work_types()
        width = self.bit_width
        pos = self.bit_pos

        check_cast(rvalue, self._ctype, r)
        field_value = set_type(
            rvalue, self._ctype.make_unqual(), il_code)
        work_value = set_type(field_value, work_signed, il_code)

        # Keep only the low `width` bits of the value, and shift them into
        # position.
        mask = (1 << width) - 1
        bits = ILValue(work_signed)
        il_code.add(math_cmds.And(
            bits, work_value, self._literal(il_code, mask, work_signed)))
        shifted_bits = ILValue(work_signed)
        self._shift(il_code, shifted_bits, bits, pos, True)

        # Read the old contents of the allocation unit and clear the bits
        # occupied by this field.
        raw = self.storage.val(il_code)
        old_work = set_type(raw, work_signed, il_code)
        all_bits = (1 << work_bits) - 1
        clear_mask = all_bits ^ (mask << pos)
        cleared = ILValue(work_signed)
        il_code.add(math_cmds.And(
            cleared, old_work,
            self._literal(il_code, clear_mask, work_signed)))

        # Combine in the new bits and write the unit back.
        new_work = ILValue(work_signed)
        il_code.add(math_cmds.Or(new_work, cleared, shifted_bits))

        new_unit = set_type(new_work, unit_unsigned, il_code)
        return self.storage.set_to(new_unit, il_code, r)


@contextmanager
def report_err():
    """Catch and add any errors to error collector."""
    try:
        yield
    except CompilerError as e:
        error_collector.add(e)


def check_cast(il_value, ctype, range):
    """Emit warnings/errors of casting il_value to given ctype.

    This method does not actually cast the values. If values cannot be
    cast, an error is raised by this method.

    il_value - ILValue to convert
    ctype - CType to convert to
    range - Range for error reporting

    """
    # Cast between compatible types is always okay
    if il_value.ctype.weak_compat(ctype):
        return

    # Cast between arithmetic types is always okay
    if ctype.is_arith() and il_value.ctype.is_arith():
        return

    # Cast between weak compatible structs is okay
    if (ctype.is_struct_union() and il_value.ctype.is_struct_union()
         and il_value.ctype.weak_compat(ctype)):
        return

    elif ctype.is_pointer() and il_value.ctype.is_pointer():

        # both operands are pointers to qualified or unqualified versions
        # of compatible types, and the type pointed to by the left has all
        # the qualifiers of the type pointed to by the right
        if (ctype.arg.weak_compat(il_value.ctype.arg)
             and (not il_value.ctype.arg.const or ctype.arg.const)):
            return

        # Cast between void pointer and pointer to object type okay
        elif (ctype.arg.is_void() and il_value.ctype.arg.is_object()
              and (not il_value.ctype.arg.const or ctype.arg.const)):
            return

        elif (ctype.arg.is_object() and il_value.ctype.arg.is_void()
              and (not il_value.ctype.arg.const or ctype.arg.const)):
            return

        # error on any other kind of pointer cast - TODO: better errors
        else:
            with report_err():
                err = "conversion from incompatible pointer type"
                raise CompilerError(err, range)
            return

    # Cast from null pointer constant to pointer okay
    elif ctype.is_pointer() and getattr(il_value.literal, "val", None) == 0:
        return

    # Cast from pointer to boolean okay
    elif ctype.is_bool() and il_value.ctype.is_pointer():
        return

    else:
        err = "invalid conversion between types"
        raise CompilerError(err, range)


def set_type(il_value, ctype, il_code, output=None):
    """If necessary, emit code to cast given il_value to the given ctype.

    If `output` is given, then this function expects output.ctype to be the
    same as ctype, sets `output` to the casted value, and returns output.

    If `output` is not given, this function returns an IL value with type
    ctype. If `il_value.ctype` matches given ctype, this function may return
    `il_value` directly. So, the return value should never have its value
    changed because this may affect the value in the given `il_value`.

    This function does no type checking and will never produce a warning or
    error.
    """
    if not output and il_value.ctype.compatible(ctype):
        return il_value
    elif output == il_value:
        return il_value
    elif not output and il_value.literal:
        output = ILValue(ctype)
        if ctype.is_integral():
            val = shift_into_range(il_value.literal.val, ctype)
        else:
            val = il_value.literal.val
        il_code.register_literal_var(output, val)
        return output
    else:
        if not output:
            output = ILValue(ctype)
        il_code.add(value_cmds.Set(output, il_value))
        return output


def arith_conversion_type(type1, type2):
    """Perform arithmetic type conversion.

    Accepts two arithmetic ctypes and returns the type these should be
    promoted to for computation.

    This functions disregards the qualifiers of the input, so it may or may
    not return a type with the same qualifier(s) as the input types.
    """
    # If an int can represent all values of the original type, the value is
    # converted to an int; otherwise, it is converted to an unsigned
    # int. These are called the integer promotions.

    # All types of size < 4 can fit in int, so we promote directly to int
    type1_promo = ctypes.integer if type1.size < 4 else type1
    type2_promo = ctypes.integer if type2.size < 4 else type2

    # If both operands have compatible types, then no further conversion is
    # needed.
    if type1_promo.weak_compat(type2_promo):
        return type1_promo

    # Otherwise, if both operands have signed integer types or both have
    # unsigned integer types, the operand with the type of lesser integer
    # conversion rank is converted to the type of the operand with greater
    # rank.
    elif type1_promo.signed == type2_promo.signed:
        return max([type1_promo, type2_promo], key=lambda t: t.size)

    # Otherwise, if the operand that has unsigned integer type has rank
    # greater or equal to the rank of the type of the other operand, then
    # the operand with signed integer type is converted to the type of the
    # operand with unsigned integer type.
    elif not type1_promo.signed and type1_promo.size >= type2_promo.size:
        return type1_promo
    elif not type2_promo.signed and type2_promo.size >= type1_promo.size:
        return type2_promo

    # Otherwise, if the type of the operand with signed integer type can
    # represent all of the values of the type of the operand with unsigned
    # integer type, then the operand with unsigned integer type is
    # converted to the type of the operand with signed integer type.
    elif type1_promo.signed and type1_promo.size > type2_promo.size:
        return type1_promo
    elif type2_promo.signed and type2_promo.size > type1_promo.size:
        return type2_promo

    # Otherwise, both operands are converted to the unsigned integer type
    # corresponding to the type of the operand with signed integer type.
    #
    # Commented because this code /should/ never be reached, because all
    # combinations will be caught by one of the above two conditions.
    #
    # elif type1_promo.signed:
    #     return type1_promo.make_unsigned()
    # elif type2_promo.signed:
    #     return type2_promo.make_unsigned()


def arith_convert(left, right, il_code):
    """Cast two arithmetic ILValues to a common converted type."""
    ctype = arith_conversion_type(left.ctype, right.ctype)
    return set_type(left, ctype, il_code), set_type(right, ctype, il_code)


def get_size(ctype, num, il_code):
    """Return ILValue representing total size of `num` objects of given ctype.

    ctype - CType of object to count
    num - Integral ILValue representing number of these objects
    """

    long_num = set_type(num, ctypes.longint, il_code)
    total = ILValue(ctypes.longint)
    size = ILValue(ctypes.longint)
    il_code.register_literal_var(size, str(ctype.size))
    il_code.add(math_cmds.Mult(total, long_num, size))

    return total


def shift_into_range(val, ctype):
    """Shift a numerical value into range for given integral ctype."""

    if ctype.signed:
        max_val = 1 << (ctype.size * 8 - 1)
        range = 2 * max_val
    else:
        max_val = 1 << ctype.size * 8
        range = max_val

    val = val % range
    if val >= max_val:
        val -= range

    return val
