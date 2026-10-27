// GCC-compiled translation unit which DEFINES thread-local objects.
//
// The ShivyC-compiled translation unit (shivyc_references.c) accesses all
// of these through extern declarations and the Initial Exec TLS model.

_Thread_local int gvar = 70;
_Thread_local int garr[4];

struct P { int x; int y; };
_Thread_local struct P gp;

_Thread_local int gzero;

void gcc_init(void) {
  garr[0] = 1;
  garr[1] = 2;
  garr[2] = 3;
  garr[3] = 4;
  gp.x = 40;
  gp.y = 41;
}

int gcc_bump_gvar(void) {
  gvar = gvar + 1;
  return gvar;
}
