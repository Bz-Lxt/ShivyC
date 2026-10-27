"""IL commands for labels, jumps, and function calls."""

import shivyc.asm_cmds as asm_cmds
import shivyc.spots as spots
from shivyc.il_cmds.base import ILCommand
from shivyc.spots import LiteralSpot


class Label(ILCommand):
    """Label - Analogous to an ASM label."""

    def __init__(self, label): # noqa D102
        """The label argument is an string label name unique to this label."""
        self.label = label

    def inputs(self): # noqa D102
        return []

    def outputs(self): # noqa D102
        return []

    def label_name(self):  # noqa D102
        return self.label

    def make_asm(self, spotmap, home_spots, get_reg, asm_code): # noqa D102
        asm_code.add(asm_cmds.Label(self.label))


class Jump(ILCommand):
    """Jumps unconditionally to a label."""

    def __init__(self, label): # noqa D102
        self.label = label

    def inputs(self): # noqa D102
        return []

    def outputs(self): # noqa D102
        return []

    def targets(self): # noqa D102
        return [self.label]

    def make_asm(self, spotmap, home_spots, get_reg, asm_code): # noqa D102
        asm_code.add(asm_cmds.Jmp(self.label))


class _GeneralJump(ILCommand):
    """General class for jumping to a label based on condition."""

    # ASM command to output for this jump IL command.
    # (asm_cmds.Je for JumpZero and asm_cmds.Jne for JumpNotZero)
    asm_cmd = None

    def __init__(self, cond, label): # noqa D102
        self.cond = cond
        self.label = label

    def inputs(self): # noqa D102
        return [self.cond]

    def outputs(self): # noqa D102
        return []

    def targets(self): # noqa D102
        return [self.label]

    def make_asm(self, spotmap, home_spots, get_reg, asm_code): # noqa D102
        size = self.cond.ctype.size

        if isinstance(spotmap[self.cond], LiteralSpot):
            r = get_reg()
            asm_code.add(asm_cmds.Mov(r, spotmap[self.cond], size))
            cond_spot = r
        else:
            cond_spot = spotmap[self.cond]

        zero_spot = LiteralSpot("0")
        asm_code.add(asm_cmds.Cmp(cond_spot, zero_spot, size))
        asm_code.add(self.command(self.label))


class JumpZero(_GeneralJump):
    """Jumps to a label if given condition is zero."""

    command = asm_cmds.Je


class JumpNotZero(_GeneralJump):
    """Jumps to a label if given condition is zero."""

    command = asm_cmds.Jne


class Return(ILCommand):
    """RETURN - returns the given value from function.

    If arg is None, then returns from the function without putting any value
    in the return register. Today, only supports values that fit in one
    register.
    """

    def __init__(self, arg=None): # noqa D102
        # arg must already be cast to return type
        self.arg = arg

    def inputs(self): # noqa D102
        return [self.arg]

    def outputs(self): # noqa D102
        return []

    def clobber(self):  # noqa D102
        return [spots.RAX]

    def abs_spot_pref(self):  # noqa D102
        return {self.arg: [spots.RAX]}

    def make_asm(self, spotmap, home_spots, get_reg, asm_code): # noqa D102
        if self.arg and spotmap[self.arg] != spots.RAX:
            size = self.arg.ctype.size
            asm_code.add(asm_cmds.Mov(spots.RAX, spotmap[self.arg], size))

        asm_code.add(asm_cmds.Mov(spots.RSP, spots.RBP, 8))
        asm_code.add(asm_cmds.Pop(spots.RBP, None, 8))
        asm_code.add(asm_cmds.Ret())


class StackSave(ILCommand):
    """Saves the current stack pointer into `output`.

    This is the counterpart to StackRestore, and is used to reclaim storage
    backing variable length arrays when a block or loop is exited.
    """

    def __init__(self, output):  # noqa D102
        self.output = output

    def inputs(self):  # noqa D102
        return []

    def outputs(self):  # noqa D102
        return [self.output]

    def make_asm(self, spotmap, home_spots, get_reg, asm_code):  # noqa D102
        output_spot = spotmap[self.output]
        # Prefer the output's own register so no move is needed when the
        # allocator placed the output in a register.
        r = get_reg([output_spot])
        asm_code.add(asm_cmds.Mov(r, spots.RSP, 8))
        if r != output_spot:
            asm_code.add(asm_cmds.Mov(output_spot, r, 8))


class StackRestore(ILCommand):
    """Restores the stack pointer from the given marker IL value."""

    def __init__(self, marker):  # noqa D102
        self.marker = marker

    def inputs(self):  # noqa D102
        return [self.marker]

    def outputs(self):  # noqa D102
        return []

    def make_asm(self, spotmap, home_spots, get_reg, asm_code):  # noqa D102
        marker_spot = spotmap[self.marker]
        # Prefer the marker's own register so the initial move is skipped
        # when the marker already lives in a register.
        r = get_reg([marker_spot])
        if r != marker_spot:
            asm_code.add(asm_cmds.Mov(r, marker_spot, 8))
        asm_code.add(asm_cmds.Mov(spots.RSP, r, 8))


class StackAlloc(ILCommand):
    """Allocates dynamic stack storage for a variable length array.

    `size` is an unsigned long IL value holding the number of bytes to
    allocate. The stack pointer is moved down by `size` bytes, rounded up
    to a 16-byte boundary, and the resulting aligned pointer is stored in
    `output`. The region below the current stack frame is overwritable.

    All fixed stack slots are addressed relative to the base pointer, so
    moving the stack pointer here does not disturb any other values.
    """

    def __init__(self, output, size):  # noqa D102
        self.output = output
        self.size = size

    def inputs(self):  # noqa D102
        return [self.size]

    def outputs(self):  # noqa D102
        return [self.output]

    def rel_spot_pref(self):  # noqa D102
        # Prefer placing the output in the same register as the size, so
        # only one temporary register is needed.
        return {self.output: [self.size]}

    def make_asm(self, spotmap, home_spots, get_reg, asm_code):  # noqa D102
        size_spot = spotmap[self.size]
        output_spot = spotmap[self.output]

        # No clobbers are declared here: every fixed stack slot is
        # addressed relative to RBP, so moving RSP does not disturb other
        # live values, and RSP is not an allocatable register.

        # The output register is always free for us to use because it is
        # defined by this command, and r may safely equal either the size
        # spot (it is overwritten before the size is consumed) or the
        # output spot.
        r = get_reg([output_spot, size_spot])

        # Round the requested size up to the next multiple of 16 so the
        # returned pointer is suitably aligned for any object type.
        if r != size_spot:
            asm_code.add(asm_cmds.Mov(r, size_spot, 8))
        asm_code.add(asm_cmds.Add(r, LiteralSpot("15"), 8))
        asm_code.add(asm_cmds.And(r, LiteralSpot("-16"), 8))
        asm_code.add(asm_cmds.Sub(spots.RSP, r, 8))

        # r is no longer needed, so reuse it to copy RSP into the output.
        asm_code.add(asm_cmds.Mov(r, spots.RSP, 8))
        if r != output_spot:
            asm_code.add(asm_cmds.Mov(output_spot, r, 8))


class Call(ILCommand):
    """Call a given function.

    func - Pointer to function
    args - Arguments of the function, in left-to-right order. Must match the
    parameter types the function expects.
    ret - If function has non-void return type, IL value to save the return
    value. Its type must match the function return value.
    """

    arg_regs = [spots.RDI, spots.RSI, spots.RDX, spots.RCX, spots.R8, spots.R9]

    def __init__(self, func, args, ret): # noqa D102
        self.func = func
        self.args = args
        self.ret = ret
        self.void_return = self.func.ctype.arg.ret.is_void()

        if len(self.args) > len(self.arg_regs):
            raise NotImplementedError("too many arguments")

    def inputs(self): # noqa D102
        return [self.func] + self.args

    def outputs(self): # noqa D102
        return [] if self.void_return else [self.ret]

    def clobber(self): # noqa D102
        # All caller-saved registers are clobbered by function call
        return [spots.RAX, spots.RCX, spots.RDX, spots.RSI, spots.RDI,
                spots.R8, spots.R9, spots.R10, spots.R11]

    def abs_spot_pref(self): # noqa D102
        prefs = {} if self.void_return else {self.ret: [spots.RAX]}
        for arg, reg in zip(self.args, self.arg_regs):
            prefs[arg] = [reg]

        return prefs

    def abs_spot_conf(self): # noqa D102
        # We don't want the function pointer to be in the same register as
        # an argument will be placed into.
        return {self.func: self.arg_regs[0:len(self.args)]}

    def indir_write(self): # noqa D102
        return self.args

    def indir_read(self): # noqa D102
        return self.args

    def make_asm(self, spotmap, home_spots, get_reg, asm_code): # noqa D102
        func_spot = spotmap[self.func]

        func_size = self.func.ctype.size
        ret_size = self.func.ctype.arg.ret.size

        # Check if function pointer spot will be clobbered by moving the
        # arguments into the correct registers.
        if spotmap[self.func] in self.arg_regs[0:len(self.args)]:
            # Get a register which isn't one of the unallowed registers.
            r = get_reg([], self.arg_regs[0:len(self.args)])
            asm_code.add(asm_cmds.Mov(r, spotmap[self.func], func_size))
            func_spot = r

        for arg, reg in zip(self.args, self.arg_regs):
            if spotmap[arg] == reg:
                continue
            asm_code.add(asm_cmds.Mov(reg, spotmap[arg], arg.ctype.size))

        asm_code.add(asm_cmds.Call(func_spot, None, self.func.ctype.size))

        if not self.void_return and spotmap[self.ret] != spots.RAX:
            asm_code.add(asm_cmds.Mov(spotmap[self.ret], spots.RAX, ret_size))
