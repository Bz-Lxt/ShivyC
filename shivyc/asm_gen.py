"""Objects for the IL->ASM stage of the compiler."""

import itertools

import shivyc.asm_cmds as asm_cmds
import shivyc.spots as spots
from shivyc.spots import Spot, RegSpot, MemSpot, LiteralSpot
from shivyc.il_cmds.control import Call
from shivyc.il_cmds.value import AddrOf, AddrRel
from shivyc.il_cmds.math import _BitShiftCmd, _DivMod


class ASMCode:
    """Stores the ASM code generated from the IL code.

    lines (List) - Lines of ASM code recorded. The commands are stored as
    tuples in this list, where the first value is the name of the command and
    the next values are the command arguments.

    """

    def __init__(self):
        """Initialize ASMCode."""
        self.lines = []
        self.comm = []
        self.globals = []
        self.data = []
        self.tdata = []
        self.tbss = []
        self.string_literals = []

    def add(self, cmd):
        """Add a command to the code.

        cmd (ASMCommand) - Command to add

        """
        self.lines.append(cmd)

    label_num = 0

    @staticmethod
    def get_label():
        """Return a unique label string."""
        ASMCode.label_num += 1
        return f"__shivyc_label{ASMCode.label_num}"

    def add_global(self, name):
        """Add a name to the code as global.

        name (str) - The name to add.

        """
        self.globals.append(f"\t.global {name}")

    def add_data(self, name, size, init):
        """Add static data to the code.

        init - the value to initialize `name` to
        """
        self.data.append(f"{name}:")
        size_strs = {1: "byte",
                     2: "word",
                     4: "int",
                     8: "quad"}

        if init:
            self.data.append(f"\t.{size_strs[size]} {init}")
        else:
            self.data.append(f"\t.zero {size}")

    def add_comm(self, name, size, local):
        """Add a common symbol to the code."""
        if local:
            self.comm.append(f"\t.local {name}")
        self.comm.append(f"\t.comm {name} {size}")

    def add_tls(self, name, size, init, external):
        """Add a defined thread-local object.

        It goes in .tdata if it has a nonzero constant initializer, and
        in .tbss otherwise.

        name (str) - Assembly name of the symbol
        size (int) - Size in bytes
        init (int or None) - Constant initializer, or None if uninitialized
        external (bool) - Whether the symbol has external linkage
        """
        lines = self.tdata if init else self.tbss
        if external:
            lines.append(f"\t.global {name}")
        else:
            lines.append(f"\t.local {name}")

        lines.append(f"{name}:")
        size_strs = {1: "byte", 2: "word", 4: "int", 8: "quad"}
        if init:
            lines.append(f"\t.{size_strs[size]} {init}")
        else:
            lines.append(f"\t.zero {size}")

    def add_string_literal(self, name, chars):
        """Add a string literal to the ASM code."""
        self.string_literals.append(f"{name}:")
        data = ",".join(str(char) for char in chars)
        self.string_literals.append(f"\t.byte {data}")

    def full_code(self):  # noqa: D202
        """Produce the full assembly code.

        return (str) - The assembly code, ready for saving to disk and
        assembling.

        """
        header = ["\t.intel_syntax noprefix"]
        header += self.comm
        if self.string_literals or self.data:
            header += ["\t.section .data"]
            header += self.data
            header += self.string_literals
            header += [""]

        if self.tdata:
            header += ["\t.section\t.tdata,\"awT\",@progbits"]
            header += self.tdata
            header += [""]

        if self.tbss:
            header += ["\t.section\t.tbss,\"awT\",@nobits"]
            header += self.tbss
            header += [""]

        header += ["\t.section .text"] + self.globals

        code = [str(line) for line in self.lines]

        footer = ["\t.section\t.note.GNU-stack,\"\",@progbits"]
        footer += ["\t.att_syntax noprefix", ""]

        return "\n".join(header + code + footer)


class NodeGraph:
    """Graph storing conflict and preference information.

    self._real_nodes - list of all real nodes in this graph
    self._all_nodes - list of all nodes in this graph, including precolored
    self.conf - dictionary mapping each node to nodes with which it
    has a conflict edge
    self._pref - dictionary mapping each node to nodes with which it
    has a preference edge

    The conflict and preference relations are symmetric. That is,
    if `n1 in self.conf[n2]`, then `n2 in self._conf[n1]` and vice versa.
    """

    def __init__(self, nodes=None):
        """Initialize NodeGraph."""
        self._real_nodes = nodes or []
        self._all_nodes = self._real_nodes[:]
        self._conf = {n: [] for n in self._all_nodes}
        self._pref = {n: [] for n in self._all_nodes}

    def is_node(self, n):
        """Check whether given node is in the graph."""
        return n in self._conf and n in self._pref

    def add_dummy_node(self, v):
        """Add a dummy node to graph."""
        self._all_nodes.append(v)
        self._conf[v] = []
        self._pref[v] = []

        # Dummy nodes must mutually conflict
        for n in self._all_nodes:
            if n not in self._real_nodes and n != v:
                self.add_conflict(n, v)

    def add_conflict(self, n1, n2):
        """Add a conflict edge between n1 and n2."""
        if n2 not in self._conf[n1]:
            self._conf[n1].append(n2)
        if n1 not in self._conf[n2]:
            self._conf[n2].append(n1)

    def add_pref(self, n1, n2):
        """Add a preference edge between n1 and n2."""
        if n2 not in self._pref[n1]:
            self._pref[n1].append(n2)
        if n1 not in self._pref[n2]:
            self._pref[n2].append(n1)

    def pop(self, n):
        """Remove and return node n from this graph."""
        del self._conf[n]
        del self._pref[n]

        if n in self._real_nodes:
            self._real_nodes.remove(n)
        self._all_nodes.remove(n)

        for v in self._conf:
            if n in self._conf[v]:
                self._conf[v].remove(n)
        for v in self._pref:
            if n in self._pref[v]:
                self._pref[v].remove(n)
        return n

    def merge(self, n1, n2):
        """Merge nodes n1 and n2.

        This function merges n2 into n1. That is, it removes n2 from the
        graph and n1 gets the preference neighbors and conflict neighbors
        that n2 previously had.
        """

        # Merge conflict lists
        total_conf = self._conf[n1][:]
        for c in self._conf[n2]:
            if c not in total_conf:
                total_conf.append(c)

        self._conf[n1] = total_conf

        # Restore symmetric invariant
        for c in self._conf[n1]:
            if n2 in self._conf[c]:
                self._conf[c].remove(n2)
            if n1 not in self._conf[c]:
                self._conf[c].append(n1)

        # Merge preference lists
        total_pref = self._pref[n1][:]
        for p in self._pref[n2]:
            if p not in total_pref:
                total_pref.append(p)

        if n1 in total_pref: total_pref.remove(n1)
        if n2 in total_pref: total_pref.remove(n2)
        self._pref[n1] = total_pref

        # Restore symmetric invariant
        for c in self._pref[n1]:
            if n2 in self._pref[c]:
                self._pref[c].remove(n2)
            if n1 not in self._pref[c]:
                self._pref[c].append(n1)

        del self._conf[n2]
        del self._pref[n2]
        self._real_nodes.remove(n2)
        self._all_nodes.remove(n2)

    def remove_pref(self, n1, n2):
        """Remove the preference edge between n1 and n2."""
        self._pref[n1].remove(n2)
        self._pref[n2].remove(n1)

    def prefs(self, n):
        """Return the list of nodes to which n has a preference edge."""
        return self._pref[n]

    def confs(self, n):
        """Return the list of nodes with which n has a conflict edge."""
        return self._conf[n]

    def nodes(self):
        """Return the real nodes currently in this graph."""
        return self._real_nodes

    def all_nodes(self):
        """Return all nodes in this graph, including pseudonodes."""
        return self._all_nodes

    def copy(self):
        """Return a deep copy of this graph, but with same ILValue objects."""
        g = NodeGraph()

        g._real_nodes = self._real_nodes[:]
        g._all_nodes = self._all_nodes[:]
        for n in self._all_nodes:
            g._conf[n] = self._conf[n][:]
            g._pref[n] = self._pref[n][:]

        return g

    def __str__(self):  # pragma: no cover
        """Return this graph as a string for debugging purposes."""
        return ("Conf\n"
                + "\n".join(str((v, self._conf[v])) for v in self._all_nodes)
                + "\nPref\n"
                + "\n".join(str((v, self._pref[v])) for v in self._all_nodes))


class ASMGen:
    """Contains the main logic for generation of the ASM from the IL.

    il_code (ILCode) - IL code to convert to ASM.
    asm_code (ASMCode) - ASMCode object to populate with ASM.
    arguments - Arguments passed via command line.
    offset (int) - Current offset from RBP for allocating on stack

    """

    # List of registers used for allocation, sorted preferred-first
    alloc_registers = spots.registers

    # List of registers used by the get_reg function.
    all_registers = alloc_registers

    def __init__(self, il_code, symbol_table, asm_code, arguments):
        """Initialize ASMGen."""
        self.il_code = il_code
        self.symbol_table = symbol_table
        self.asm_code = asm_code
        self.arguments = arguments

        self.offset = 0

    def make_asm(self):
        """Generate ASM code."""
        global_spotmap = self._get_global_spotmap()
        for func in self.il_code.commands:
            self.asm_code.add(asm_cmds.Label(func))
            self._make_asm(self.il_code.commands[func], global_spotmap)

    def _make_asm(self, commands, global_spotmap):
        """Generate ASM code for given command list."""

        # Get free values
        free_values = self._get_free_values(commands, global_spotmap)

        # If any variable may have its address referenced, assign it a
        # permanent memory spot if it doesn't yet have one.
        move_to_mem = []
        for command in commands:
            refs = command.references().values()
            for line in refs:
                for v in line:
                    if v not in refs:
                        move_to_mem.append(v)

        # In addition, move all IL values of strange size to memory because
        # they won't fit in a register.
        for v in free_values:
            if v.ctype.size not in {1, 2, 4, 8}:
                move_to_mem.append(v)

        # TODO: All non-free IL values are automatically assigned distinct
        # memory spots. However, this is very inoptimal for structs.
        # Consider the following C code, where S is already declared:
        #
        #   struct S array[10];
        #   s = array[1];
        #
        # This code compiles to the following IL:
        #
        #   READAT(array, 1) -> X
        #   SET(X) -> s
        #
        # However, X is an unnecessary copy of `s` in memory. Ideally,
        # the register allocator will recognize that X is just a temporary
        # and assign X to the same memory location as s to avoid additional
        # copy operations and memory usage. This also requires that the
        # relevant IL commands check whether the two arguments are in the
        # same spot before trying to do a copy.
        for v in move_to_mem:
            if v in free_values:
                self.offset += v.ctype.size
                global_spotmap[v] = MemSpot(spots.RBP, -self.offset)
                free_values.remove(v)

        # Perform liveliness analysis
        live_vars = self._get_live_vars(commands, free_values)

        # Generate conflict and preference graph
        g_bak = self._generate_graph(commands, free_values, live_vars)

        spilled_nodes = []

        while True:
            g = g_bak.copy()

            # Remove all nodes that have been spilled for this iteration
            for n in spilled_nodes:
                g.pop(n)

            removed_nodes = []
            merged_nodes = {}

            # Repeat simplification, coalescing, and freeze until freeze
            # does not work.
            while True:
                # Repeat simplification and coalescing until nothing
                # happens.
                while True:
                    simplified = self._simplify_all(removed_nodes, g)
                    merged = self._coalesce_all(merged_nodes, g)

                    if not simplified and not merged: break

                if not self._freeze(g):
                    break

            # If no nodes remain, we are done
            if not g.nodes():
                break
            # If nodes do remain, spill one of them and retry
            else:
                # Spill node with highest number of conflicts. This node
                # will never be a merged node because we merge nodes
                # conservatively, so any recently merged node can be
                # simplified immediately.
                n = max(g.nodes(), key=lambda n: len(g.confs(n)))
                spilled_nodes.append(n)

        # Move any remaining nodes from graph into removed_nodes
        # This accounts for pseudonodes which cannot be removed in the
        # simplify phase.
        while g.all_nodes():
            removed_nodes.append(g.pop(g.all_nodes()[0]))

        # Pop values off the stack to generate spot assignments.
        spotmap = self._generate_spotmap(removed_nodes, merged_nodes, g_bak)

        # Assign stack values to the spilled nodes
        for v in spilled_nodes:
            self.offset += v.ctype.size
            spotmap[v] = MemSpot(spots.RBP, -self.offset)

        # Merge global spotmap into this spotmap
        for v in global_spotmap:
            spotmap[v] = global_spotmap[v]

        if self.arguments.show_reg_alloc_perf:  # pragma: no cover
            total_prefs = 0
            matched_prefs = 0

            for n1, n2 in itertools.combinations(g_bak.all_nodes(), 2):
                if n2 in g_bak.prefs(n1):
                    total_prefs += 1
                    if spotmap[n1] == spotmap[n2]:
                        matched_prefs += 1

            print("total prefs", total_prefs)
            print("matched prefs", matched_prefs)

            print("total ILValues", len(g_bak.nodes()))
            print("register ILValues", len(g_bak.nodes()) - len(spilled_nodes))

        # Generate assembly code
        self._generate_asm(commands, live_vars, spotmap)

    def _get_global_spotmap(self):
        """Generate global spotmap and add global values to ASM.

        This function generates a spotmap for variables which are not
        specific to a single function. This includes literals and variables
        with static storage duration.
        """
        global_spotmap = {}

        EXTERNAL = self.symbol_table.EXTERNAL
        DEFINED = self.symbol_table.DEFINED

        num = 0

        for value in (set(self.il_code.literals.keys())
                      | set(self.il_code.string_literals.keys())
                      | set(self.symbol_table.storage.keys())):
            num += 1
            spot = self._get_nondynamic_spot(value, num)
            if spot: global_spotmap[value] = spot

        externs = self.symbol_table.linkages[EXTERNAL].values()
        for v in externs:
            if self.symbol_table.def_state.get(v) == DEFINED:
                self.asm_code.add_global(self.symbol_table.names[v])

        return global_spotmap

    def _get_nondynamic_spot(self, v, num):
        """Get a spot for non-dynamic values.

        In particular, assigns a spot to all literals, string literals,
        variables with no storage, and variables with static storage.

        v - value to get a spot for, or None if the value goes in a dynamic
        spot like a register
        nnum - positive integer guaranteed never to be the same for two
        distinct calls to this function
        """
        EXTERNAL = self.symbol_table.EXTERNAL
        INTERNAL = self.symbol_table.INTERNAL
        TENTATIVE = self.symbol_table.TENTATIVE
        THREAD = self.symbol_table.THREAD

        if v in self.il_code.literals:
            return LiteralSpot(self.il_code.literals[v])

        elif v in self.il_code.string_literals:
            name = f"__strlit{num}"
            self.asm_code.add_string_literal(
                name, self.il_code.string_literals[v])
            return MemSpot(name)

        # A thread-local object which is only declared, not defined, in this
        # translation unit. The Initial Exec model resolves it through the
        # GOT entry produced by the linker.
        elif (self.symbol_table.thread.get(v)
              and not self.symbol_table.storage.get(v, None)):
            return spots.TLSMemSpot(self.symbol_table.names[v], "IE")

        # Values with no storage can be referenced directly by name
        elif not self.symbol_table.storage.get(v, True):
            return MemSpot(self.symbol_table.names[v])

        elif self.symbol_table.storage.get(v) == THREAD:
            linkage = self.symbol_table.linkage_type.get(v)
            external = linkage == EXTERNAL

            name = self.symbol_table.names[v]
            if not external:
                # Rename symbols with internal or no linkage so they can
                # never clash with anything from another translation unit.
                name = f"{name}.{num}"

            # A tentative definition of a thread-local object is emitted as
            # an ordinary zero-initialized definition in .tbss, just like
            # GCC does. As in GCC, defining the same object tentatively in
            # another translation unit is a multiple-definition error at
            # link time.
            init_val = self.il_code.static_inits.get(v, None)
            self.asm_code.add_tls(
                name, v.ctype.size, init_val, external)

            # The executable's own definitions always use the Local Exec
            # model; the static linker resolves the TPOFF directly, even for
            # symbols with external linkage, exactly as it does for GCC.
            return spots.TLSMemSpot(name, "LE")

        elif self.symbol_table.storage.get(v) == self.symbol_table.STATIC:
            name = self.symbol_table.names[v]
            if self.symbol_table.linkage_type.get(v) != EXTERNAL:
                name = f"{name}.{num}"

            if self.symbol_table.def_state.get(v) == TENTATIVE:
                local = (self.symbol_table.linkage_type[v] == INTERNAL)
                self.asm_code.add_comm(name, v.ctype.size, local)
            else:
                init_val = self.il_code.static_inits.get(v, 0)
                self.asm_code.add_data(name, v.ctype.size, init_val)

            return MemSpot(name)

    def _get_free_values(self, commands, global_spotmap):
        """Generate list of free values.

        Returns a list of the free values, the variables which need
        allocation on the stack.
        """
        free_values = []
        for command in commands:
            for value in command.inputs() + command.outputs():
                if (value and value not in free_values
                      and value not in global_spotmap):
                    free_values.append(value)

        return free_values

    def _get_live_vars(self, commands, free_values):
        """Given a set of free ILValues, find when those ILValues are live.

        free_values - list of ILValues for which to perform liveliness analysis
        returns - array mapping command indices to a tuple where first
        element is a list of variables live coming into the command and the
        second is a list of the variables live exiting the command
        """
        # Preprocess all commands to get a mapping from labels to command
        # number.
        labels = {c.label_name(): i for i, c in enumerate(commands)
                  if c.label_name()}

        # Last iteration of live variables
        prev_live_vars = None

        # This iteration of live variables
        live_vars = [([], []) for i in range(len(commands))]

        while live_vars != prev_live_vars:
            prev_live_vars = live_vars[:]

            # List of currently live variables
            cur_live = []

            # Iterate through commands in backwards order
            for i, command in list(enumerate(commands))[::-1]:
                # If current command is a jump, add the live inputs of all
                # possible targets to the current live list.
                for label in command.targets():
                    i2 = labels[label]
                    for v in prev_live_vars[i2][0]:
                        if v not in cur_live:
                            cur_live.append(v)

                # Variables live on output from this command
                out_live = cur_live[:]

                # Add variables used in this command to current live variables
                for v in command.inputs():
                    if v in free_values and v not in cur_live:
                        cur_live.append(v)

                # Remove variables defined in this command to live variables
                for v in command.outputs():
                    if v in free_values:
                        if v in cur_live:
                            cur_live.remove(v)
                        else:
                            # If variable is defined in command but was not
                            # live, make it live on output from this command.

                            # TODO: Deal with this more efficiently.
                            # If the output is not live, then we don't actually
                            # need to perform this computation.
                            out_live.append(v)

                # Variables live on input from this command
                in_live = cur_live[:]

                live_vars[i] = (in_live, out_live)

        return live_vars

    def _generate_graph(self, commands, free_values, live_vars):
        """Generate the conflict/preference graph.

        free_values - List of ILValues to include in the graph
        live_vars - Live range information from _get_live_vars

        """
        g = NodeGraph(free_values)
        for i, command in enumerate(commands):
            # Variables active during input
            for n1, n2 in itertools.combinations(live_vars[i][0], 2):
                g.add_conflict(n1, n2)

            # Variables active during output
            for n1, n2 in itertools.combinations(live_vars[i][1], 2):
                g.add_conflict(n1, n2)

            # Relative conflict set of this command
            for n1 in command.rel_spot_conf():
                for n2 in command.rel_spot_conf()[n1]:
                    if n1 in free_values and n2 in free_values:
                        g.add_conflict(n1, n2)

            # Absolute conflict set of this command
            for n in command.abs_spot_conf():
                for s in command.abs_spot_conf()[n]:
                    if n in free_values:
                        if s not in g.all_nodes():
                            g.add_dummy_node(s)
                        g.add_conflict(n, s)

            # Clobber set of this command
            for s in command.clobber():
                if s not in g.all_nodes():
                    g.add_dummy_node(s)

                # Add a conflict with dummy node for every variable live
                # during both entry and exit from this command.
                for n in live_vars[i][0]:
                    if n in live_vars[i][1]:
                        g.add_conflict(n, s)

            # Form preferences based on rel_spot_pref
            for v1 in command.rel_spot_pref():
                for v2 in command.rel_spot_pref()[v1]:
                    if g.is_node(v1) and g.is_node(v2):
                        g.add_pref(v1, v2)

            # Form preferences based on abs_spot_pref
            for v in command.abs_spot_pref():
                for s in command.abs_spot_pref()[v]:
                    if v in free_values:
                        if s not in g.all_nodes():
                            g.add_dummy_node(s)
                        g.add_pref(v, s)
        return g

    def _simplify_all(self, removed_nodes, g):
        """Repeat the Simplify step until no more can be done.

        Returns False iff no simplification is done.

        removed_nodes - stack of removed nodes to which this function adds
        the nodes it removes
        """

        # Get nodes without preference edges
        no_pref = [v for v in g.nodes() if not g.prefs(v)]

        # Repeat simplification until no more nodes can be removed
        did_something = False
        while True:
            rem = self._simplify_once(no_pref, g)
            if rem:
                removed_nodes.append(rem)
                no_pref.remove(rem)
                did_something = True
            else:
                break

        return did_something

    def _simplify_once(self, nodes, g):
        """Remove and return a node in nodes if it has low conflict degree."""
        for v in nodes:
            # If the node has low conflict degree remove it from the graph
            if len(g.confs(v)) < len(self.alloc_registers):
                return g.pop(v)

    def _coalesce_all(self, merged_nodes, g):
        """Repeat the coalesce step until no more can be done.

        Returns False iff no simplification is done.

        merged_nodes - Mapping from node to list of nodes. Every node in the
        list of nodes has been merged into the key node.
        """
        did_something = False
        while True:
            merge = self._coalesce_once(g)
            if merge:
                if merge[0] not in merged_nodes:
                    merged_nodes[merge[0]] = []

                merged_nodes[merge[0]].append(merge[1])
                did_something = True
            else:
                break

        return did_something

    def _coalesce_once(self, g):
        """Perform one iteration of the coalesce step.

        Returns the merged pair if a merge was successfully completed. The
        first element is the preserved node, and the second element is the
        removed node.
        """
        for v1 in g.nodes():
            for v2 in g.prefs(v1):
                # If the two nodes conflict, automatically continue.
                if v1 in g.confs(v2):
                    continue

                total_confs = len(set(g.confs(v1)) | set(g.confs(v2)))

                # If one is a spot, use a special heuristic.
                # (described on section 6, page 311 of George & Appel)
                if isinstance(v1, Spot):
                    v1, v2 = v2, v1
                if isinstance(v2, Spot):
                    for T in g.confs(v1):
                        if v2 in g.confs(T):
                            continue
                        if len(g.confs(T)) < len(self.alloc_registers):
                            continue
                        break
                    else:
                        # We can merge v1 into v2.
                        g.merge(v2, v1)
                        return v2, v1

                # Otherwise, apply regular merging rules.
                elif total_confs < len(self.alloc_registers):
                    g.merge(v1, v2)
                    return v1, v2

    def _freeze(self, g):
        """Remove one preference edge.

        This function finds two nodes, preferably of low conflict degree,
        that are connected by a preference edge. Then, this preference edge
        is removed from the graph. Returns false iff nothing is done.
        """

        # Sort a list of nodes by conflict degree
        nodes = sorted(g.all_nodes(), key=lambda n: len(g.confs(n)))
        index_pairs = list(itertools.combinations(list(enumerate(nodes)), 2))

        # Sort pairs to prioritize nodes which appear earlier in `nodes`
        index_pairs.sort(key=lambda p: p[0][0] + p[1][0])

        # Extract just the node pairs
        pairs = [(p[0][1], p[1][1]) for p in index_pairs]

        # Now, the earlier pairs in `pairs` have lower conflict degree and
        # are thus superior candidates for freezing.
        for n1, n2 in pairs:
            if n1 in g.prefs(n2):
                g.remove_pref(n1, n2)
                return True

        return False

    def _generate_spotmap(self, removed_nodes, merged_nodes, g):
        """Pop values off stack to generate spot assignments."""

        # Get a set of nodes which interfere with n or anything merged into it
        def get_conflicts(n):
            conflicts = set(g.confs(n))
            for n1 in merged_nodes.get(n, []):
                conflicts |= get_conflicts(n1)
            return conflicts

        # Get a set of nodes which are merged into `n`
        def get_merged(n):
            merged = {n}
            for n1 in merged_nodes.get(n, []):
                merged |= get_merged(n1)
            return merged

        # Build up spotmap
        spotmap = {}
        i = 0
        while removed_nodes:
            i += 1

            # Allocate register to node `n`
            n1 = removed_nodes.pop()
            regs = self.alloc_registers[::-1]

            # If n1 is a Spot (i.e. dummy node), immediately assign it a
            # register.
            if n1 in regs:
                reg = n1
            else:
                # Don't chose any conflicting spots
                for n2 in get_conflicts(n1):
                    # If n2 is a physical spot
                    if n2 in regs:
                        regs.remove(n2)
                    if n2 in spotmap and spotmap[n2] in regs:
                        regs.remove(spotmap[n2])

                # Based on algorithm, there should always be register remaining
                reg = regs.pop()

            # Assign this register to every node merged into n1
            for n2 in get_merged(n1):
                spotmap[n2] = reg

        return spotmap

    def _generate_asm(self, commands, live_vars, spotmap):
        """Generate assembly code."""

        # This is kinda hacky...
        max_offset = max(spot.rbp_offset() for spot in spotmap.values())
        if max_offset % 16 != 0:
            max_offset += 16 - max_offset % 16

        # Back up rbp and move rsp
        self.asm_code.add(asm_cmds.Push(spots.RBP, None, 8))
        self.asm_code.add(asm_cmds.Mov(spots.RBP, spots.RSP, 8))

        offset_spot = LiteralSpot(str(max_offset))
        self.asm_code.add(asm_cmds.Sub(spots.RSP, offset_spot, 8))

        # Generate code for each command
        for i, command in enumerate(commands):
            self.asm_code.add(asm_cmds.Comment(type(command).__name__.upper()))

            # Registers currently holding TPOFFs of Initial Exec thread-local
            # variables for this command. The get_reg closure is made aware
            # of them so command-emitted code cannot clobber one.
            tls_regs = []

            def get_reg(pref=None, conf=None, strict=False):
                if not pref: pref = []
                if not conf: conf = []

                # Normally a spot is bad only if it holds a variable live
                # both entering and exiting this command. Scratch registers
                # loaded before the command starts (e.g. thread-local TPOFF
                # registers) must not clobber any live-in spot at all.
                if strict:
                    bad_vars = set(live_vars[i][0])
                else:
                    bad_vars = set(live_vars[i][0]) & set(live_vars[i][1])
                bad_spots = set(spotmap[var] for var in bad_vars)

                # Spot is free if it is where an output is stored.
                for v in command.outputs():
                    bad_spots.discard(spotmap[v])

                # Spot is bad if it is listed as a conflicting spot, or if
                # it holds a thread-local TPOFF needed by this command.
                bad_spots |= set(conf)
                bad_spots |= set(tls_regs)

                for s in (pref + self.all_registers):
                    if isinstance(s, RegSpot) and s not in bad_spots:
                        return s

                raise NotImplementedError("spill required for get_reg")

            # Taking the address of a thread-local object produces an
            # ordinary linear pointer, so this is handled specially.
            if (isinstance(command, AddrOf)
                    and isinstance(spotmap.get(command.var),
                                   spots.TLSMemSpot)):
                self._make_addr_of_asm(command, spotmap, get_reg)
            elif (isinstance(command, AddrRel)
                    and isinstance(spotmap.get(command.base),
                                   spots.TLSMemSpot)):
                self._make_addr_rel_asm(command, spotmap, get_reg)
            # Calls need special handling because a TPOFF loaded for the
            # return value would not survive the call itself.
            elif isinstance(command, Call):
                self._make_call_asm(command, spotmap, get_reg, tls_regs)
            else:
                tls_spotmap = self._resolve_tls_spots(
                    command, spotmap, get_reg, tls_regs)
                command.make_asm(tls_spotmap, tls_spotmap, get_reg,
                                 self.asm_code)

    def _resolve_tls_spots(self, command, spotmap, get_reg, tls_regs):
        """Resolve thread-local spots referenced by command.

        Local Exec operands need no register at all: they are replaced by
        spots which render directly as fs:-relative references. Initial
        Exec operands require loading the TPOFF from the GOT into a
        register, which is then used inside an fs: segment override.

        The TPOFF-holding registers are tracked in tls_regs so that the
        command's own code cannot overwrite them.
        """
        # Some commands write fixed registers while their operands are still
        # being read, so such registers cannot hold a TPOFF.
        forbidden = set()
        if isinstance(command, _BitShiftCmd):
            forbidden.add(spots.RCX)
        if isinstance(command, _DivMod):
            forbidden |= {spots.RAX, spots.RDX}

        # The TPOFF register must also differ from any register output of
        # this command. Otherwise the access aliases its base and its
        # destination (or written value), as in `mov ecx, DWORD PTR
        # fs:[rcx]`, which is legal hardware-wise but is translated
        # incorrectly by some x86_64 emulators.
        for v in command.outputs():
            if v is not None and isinstance(spotmap.get(v), RegSpot):
                forbidden.add(spotmap[v])

        # Collect the distinct TLS spots this command touches. Inputs and
        # outputs are scanned directly because some commands (e.g. the
        # relative commands) do not list every operand through references().
        tls_spots = []
        for v in command.inputs() + command.outputs():
            if v is None:
                continue
            spot = spotmap.get(v)
            if isinstance(spot, spots.TLSMemSpot) and spot not in tls_spots:
                tls_spots.append(spot)

        tls_spotmap = dict(spotmap)

        for tls_spot in tls_spots:
            if tls_spot.model == "LE":
                resolved = spots.TLSLESpot(tls_spot.name)
            elif tls_spot.model == "IE":
                reg = get_reg(conf=tls_regs + list(forbidden), strict=True)
                tls_regs.append(reg)
                self.asm_code.add(
                    asm_cmds.Mov(reg, spots.GOTTPOFFSpot(tls_spot.name), 8))
                resolved = spots.TLSIESpot(reg)
            else:
                raise NotImplementedError(
                    f"unknown TLS model '{tls_spot.model}'")

            for v in command.inputs() + command.outputs():
                if v is not None and spotmap.get(v) == tls_spot:
                    tls_spotmap[v] = resolved

        return tls_spotmap

    def _make_addr_of_asm(self, command, spotmap, get_reg):
        """Emit an AddrOf command for a thread-local variable.

        The result is an ordinary linear pointer and can be passed around
        like any other address.
        """
        tls_spot = spotmap[command.var]
        out_spot = spotmap[command.output]

        out_in_reg = isinstance(out_spot, RegSpot)

        if tls_spot.model == "LE":
            if out_in_reg:
                addr_reg = out_spot
                tp_reg = get_reg(conf=[addr_reg], strict=True)
                self.asm_code.add(
                    asm_cmds.Mov(tp_reg, spots.TPBaseSpot(), 8))
                self.asm_code.add(
                    asm_cmds.Lea(addr_reg,
                                 spots.TLSLEAddrSpot(tls_spot.name, tp_reg)))
            else:
                addr_reg = get_reg(strict=True)
                tp_reg = get_reg(conf=[addr_reg], strict=True)
                self.asm_code.add(
                    asm_cmds.Mov(tp_reg, spots.TPBaseSpot(), 8))
                self.asm_code.add(
                    asm_cmds.Lea(addr_reg,
                                 spots.TLSLEAddrSpot(tls_spot.name, tp_reg)))
                self.asm_code.add(
                    asm_cmds.Mov(out_spot, addr_reg,
                                 command.output.ctype.size))
        elif tls_spot.model == "IE":
            if out_in_reg:
                addr_reg = out_spot
            else:
                addr_reg = get_reg(strict=True)

            tp_reg = get_reg(conf=[addr_reg], strict=True)
            self.asm_code.add(
                asm_cmds.Mov(addr_reg, spots.GOTTPOFFSpot(tls_spot.name), 8))
            self.asm_code.add(
                asm_cmds.Mov(tp_reg, spots.TPBaseSpot(), 8))
            self.asm_code.add(asm_cmds.Add(addr_reg, tp_reg, 8))

            if not out_in_reg:
                self.asm_code.add(
                    asm_cmds.Mov(out_spot, addr_reg,
                                 command.output.ctype.size))
        else:
            raise NotImplementedError(
                f"unknown TLS model '{tls_spot.model}'")

    def _make_addr_rel_asm(self, command, spotmap, get_reg):
        """Emit an AddrRel command for a thread-local base.

        Produces an ordinary linear pointer to an element or member of a
        thread-local object, following the forms used by GCC.
        """
        tls_spot = spotmap[command.base]
        out_spot = spotmap[command.output]
        out_in_reg = isinstance(out_spot, RegSpot)
        out_r = out_spot if out_in_reg else get_reg(strict=True)

        # Resolve the count register, or fold a literal count into the
        # constant displacement.
        count_r = None
        if command.count:
            disp = 0
            cspot = spotmap[command.count]
            if isinstance(cspot, LiteralSpot):
                disp = command.chunk * int(cspot.value)
            elif isinstance(cspot, RegSpot):
                count_r = cspot
            else:
                count_r = get_reg(conf=[out_r], strict=True)
                self.asm_code.add(
                    asm_cmds.Mov(count_r, cspot,
                                 command.count.ctype.size))
        else:
            disp = command.chunk

        # The second lea below indexes by count_r while accumulating into
        # out_r, so count_r must be a distinct register.
        if count_r == out_r:
            count_r = get_reg(conf=[out_r], strict=True)
            self.asm_code.add(
                asm_cmds.Mov(count_r, spotmap[command.count],
                             command.count.ctype.size))

        if tls_spot.model == "LE":
            tp_reg = get_reg(conf=[out_r, count_r], strict=True)
            self.asm_code.add(
                asm_cmds.Mov(tp_reg, spots.TPBaseSpot(), 8))
            self.asm_code.add(
                asm_cmds.Lea(out_r,
                             spots.TLSLEAddrSpot(tls_spot.name, tp_reg, disp)))
            if count_r:
                self.asm_code.add(
                    asm_cmds.Lea(
                        out_r, MemSpot(out_r, 0, command.chunk, count_r)))
        elif tls_spot.model == "IE":
            tp_reg = get_reg(conf=[out_r, count_r], strict=True)
            got_reg = get_reg(conf=[out_r, tp_reg, count_r], strict=True)
            self.asm_code.add(
                asm_cmds.Mov(got_reg, spots.GOTTPOFFSpot(tls_spot.name), 8))
            self.asm_code.add(
                asm_cmds.Mov(tp_reg, spots.TPBaseSpot(), 8))
            self.asm_code.add(
                asm_cmds.Lea(out_r, MemSpot(got_reg, disp, 1, tp_reg)))
            if count_r:
                self.asm_code.add(
                    asm_cmds.Lea(
                        out_r, MemSpot(out_r, 0, command.chunk, count_r)))
        else:
            raise NotImplementedError(
                f"unknown TLS model '{tls_spot.model}'")

        if not out_in_reg:
            self.asm_code.add(
                asm_cmds.Mov(out_spot, out_r, command.output.ctype.size))

    def _make_call_asm(self, command, spotmap, get_reg, tls_regs):
        """Emit a Call command with thread-local arguments or return value.

        Local Exec arguments need no register at all. Initial Exec argument
        TPOFFs are loaded before arguments are marshalled, using registers
        distinct from all argument registers. A thread-local return value
        is written only after the call returns.
        """
        tls_spotmap = dict(spotmap)

        # A TPOFF register must never be an argument register or hold the
        # function pointer.
        func_spot = spotmap[command.func]
        forbidden = list(command.arg_regs[0:len(command.args)])
        if isinstance(func_spot, RegSpot):
            forbidden.append(func_spot)

        for arg in command.args:
            arg_spot = spotmap.get(arg)
            if isinstance(arg_spot, spots.TLSMemSpot):
                if arg_spot.model == "LE":
                    tls_spotmap[arg] = spots.TLSLESpot(arg_spot.name)
                elif arg_spot.model == "IE":
                    reg = get_reg(conf=tls_regs + forbidden, strict=True)
                    tls_regs.append(reg)
                    self.asm_code.add(
                        asm_cmds.Mov(reg, spots.GOTTPOFFSpot(arg_spot.name),
                                     8))
                    tls_spotmap[arg] = spots.TLSIESpot(reg)
                else:
                    raise NotImplementedError(
                        f"unknown TLS model '{arg_spot.model}'")

        ret_tls_spot = None
        if not command.void_return:
            ret_spot = spotmap.get(command.ret)
            if isinstance(ret_spot, spots.TLSMemSpot):
                ret_tls_spot = ret_spot
                # Make Call.make_asm skip its own move of RAX into the
                # thread-local return variable; it is emitted below, after
                # the call returns.
                tls_spotmap[command.ret] = spots.RAX

        command.make_asm(tls_spotmap, tls_spotmap, get_reg, self.asm_code)

        if ret_tls_spot:
            size = command.func.ctype.arg.ret.size
            if ret_tls_spot.model == "LE":
                self.asm_code.add(
                    asm_cmds.Mov(spots.TLSLESpot(ret_tls_spot.name),
                                 spots.RAX, size))
            elif ret_tls_spot.model == "IE":
                reg = get_reg(conf=[spots.RAX])
                self.asm_code.add(
                    asm_cmds.Mov(reg,
                                 spots.GOTTPOFFSpot(ret_tls_spot.name), 8))
                self.asm_code.add(
                    asm_cmds.Mov(spots.TLSIESpot(reg), spots.RAX, size))
            else:
                raise NotImplementedError(
                    f"unknown TLS model '{ret_tls_spot.model}'")
