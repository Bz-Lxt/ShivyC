// Variable length arrays (C11).
//
// This exercises runtime-sized arrays inside functions: read/write of
// one-dimensional VLAs, multi-dimensional indexing, runtime sizeof,
// recursion, stack reclamation after break/continue and block exit, and
// coexistence with fixed-length arrays.
//
// Return: 0

int vla_sum(int n) {
  int a[n];
  int i;
  for (i = 0; i < n; i++) a[i] = i + 1;

  if (sizeof a != (unsigned long)n * 4) return 1;
  if (sizeof a[0] != 4) return 2;

  int sum = 0;
  for (i = 0; i < n; i++) sum += a[i];
  return sum;
}

int matrix_sum(int n, int m, int a[n][m]) {
  int sum = 0;
  int i, j;
  for (i = 0; i < n; i++)
    for (j = 0; j < m; j++)
      sum += a[i][j];
  return sum;
}

// Each recursive frame owns a VLA of a different size. The values stored
// in a caller frame must survive the callee frame allocating its own VLA.
int rec_check(int depth) {
  int a[depth + 1];
  int i;
  for (i = 0; i <= depth; i++) a[i] = depth * 1000 + i;

  int below;
  if (depth == 0) {
    below = 0;
  } else {
    below = rec_check(depth - 1);
  }

  for (i = 0; i <= depth; i++)
    if (a[i] != depth * 1000 + i) return 100 + depth;
  return below;
}

int main() {
  // One-dimensional VLA.
  if (vla_sum(10) != 55) return 3;
  if (vla_sum(20) != 210) return 4;

  // Two-dimensional VLA with multi-dimensional indexing and sizeof.
  int n = 6;
  int m = 9;
  int b[n][m];
  int i, j;
  for (i = 0; i < n; i++)
    for (j = 0; j < m; j++)
      b[i][j] = i * m + j;

  if (sizeof b != (unsigned long)n * m * 4) return 5;
  if (sizeof b[0] != (unsigned long)m * 4) return 6;
  if (sizeof b[0][0] != 4) return 7;

  // Runtime sizeof of an abstract VLA type and of the whole-array object.
  if (sizeof(int[n][m]) != (unsigned long)n * m * 4) return 20;
  if (sizeof *(&b) != (unsigned long)n * m * 4) return 21;

  for (i = 0; i < n; i++)
    for (j = 0; j < m; j++)
      if (b[i][j] != i * m + j) return 8;

  // VLA passed as a variably-modified parameter.
  if (matrix_sum(n, m, b) != (n * m - 1) * n * m / 2) return 9;

  // Pointer to a variable length array.
  int (*p)[m];
  p = &b[4];
  (*p)[2] = 777;
  if (b[4][2] != 777) return 10;
  if (p[1][0] != b[5][0]) return 11;
  if (sizeof *p != (unsigned long)m * 4) return 12;

  // Increment, decrement, compound assignment, and subtraction on
  // pointers to a variable length array use the runtime element size.
  int (*q)[m];
  q = &b[0];
  q++;
  if (q[0][1] != b[1][1]) return 22;
  q--;
  if (&q[0] != &b[0]) return 23;

  int (*rlo)[m];
  int (*rhi)[m];
  rlo = &b[1];
  rhi = &b[3];
  if (rhi - rlo != 2) return 24;

  q += 3;
  if (q[0][0] != b[3][0]) return 25;

  // Pointer to the whole two-dimensional VLA, stepped by the runtime
  // size of an entire n by m matrix.
  int (*whole)[n][m];
  whole = &b;
  (*whole)[5][8] = 999;
  if (b[5][8] != 999) return 28;

  char *base = (char *)&b;
  char *after = (char *)(whole + 1);
  if (after - base != n * m * 4) return 29;
  if (sizeof **whole != (unsigned long)m * 4) return 30;

  // Recursive frames with VLAs.
  if (rec_check(20) != 0) return 13;

  // VLAs in nested loops with break and continue must be reclaimed each
  // iteration, and values in outer arrays must remain intact.
  int outer_bad = 0;
  for (i = 0; i < 4; i++) {
    int v[30 + i];
    v[29 + i] = i + 11;
    int k;
    for (k = 0; k < 50; k++) {
      int w[k + 1];
      w[0] = 7;
      w[k] = k + 7;
      if (w[k] != k + 7) outer_bad += 1;
      if (k == 5) break;
      if (k == 1) continue;
      if (w[0] != 7) outer_bad += 1;
    }
    if (v[29 + i] != i + 11) outer_bad += 1;
  }
  if (outer_bad) return 14;

  // A VLA declared in a loop body must not grow the stack without bound.
  // If storage were not reclaimed each iteration, these loops would
  // exhaust the stack: the while loop uses continue on every iteration,
  // and the for loop uses break on its last iteration.
  int w_iters = 40000;
  i = 0;
  while (i < w_iters) {
    int wtmp[2000];
    wtmp[0] = i;
    wtmp[1999] = i + 1;
    if (wtmp[0] != i) return 15;
    if (wtmp[1999] != i + 1) return 15;
    i++;
    continue;
  }

  i = 0;
  while (1) {
    int wtmp[2000];
    wtmp[1999] = 555;
    if (i == 3) {
      if (wtmp[1999] != 555) return 26;
      break;
    }
    i++;
  }

  int f_iters = 40000;
  for (i = 0; i < f_iters; i++) {
    int tmp[2000];
    tmp[0] = i;
    tmp[1999] = i + 2;
    if (i == f_iters - 1) {
      if (tmp[0] != f_iters - 1) return 27;
      if (tmp[1999] != f_iters + 1) return 27;
      break;
    }
    continue;
  }

  // Block-scope VLA storage is released when the block ends, while fixed
  // local variables keep their values.
  int guard = 4321;
  {
    int q[300];
    q[299] = 7;
  }
  if (guard != 4321) return 16;

  // A variable declared in the first clause of a for loop lives for the
  // whole loop, so its VLA storage persists across iterations and is
  // reclaimed only after the loop finishes.
  int seen = 0;
  int k = 0;
  for (int keep[k + 3]; k < 3; k++) {
    keep[k] = k + 20;
    if (keep[0] != 20) seen += 1;
  }
  if (seen) return 17;

  // Fixed-length arrays keep their old behavior next to VLAs.
  int fixed[5];
  for (i = 0; i < 5; i++) fixed[i] = i * i;
  if (sizeof fixed != 20) return 18;
  if (fixed[4] != 16) return 19;

  return 0;
}
