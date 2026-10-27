// ShivyC-compiled translation unit which REFERENCES thread-local objects
// defined by GCC in gcc_defines.c.

extern _Thread_local int gvar;
extern _Thread_local int garr[];

struct P { int x; int y; };
extern _Thread_local struct P gp;

extern _Thread_local int gzero;

void gcc_init();
int gcc_bump_gvar();

int main() {
  gcc_init();

  if (gvar != 70) return 1;
  gvar = gvar + 1;
  if (gcc_bump_gvar() != 72) return 2;
  if (gvar != 72) return 3;

  int i;
  for (i = 0; i < 4; i++) {
    if (garr[i] != i + 1) return 10 + i;
  }

  if (gp.x != 40) return 20;
  if (gp.y != 41) return 21;
  gp.x = gp.x + gzero;
  if (gp.x != 40) return 22;
  if (gzero != 0) return 23;

  // 72 + 4 + 41 = 117
  // Return: 117
  return gvar + garr[3] + gp.y;
}
