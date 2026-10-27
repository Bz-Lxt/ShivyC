// ShivyC-compiled translation unit which DEFINES thread-local objects.
//
// The GCC-compiled translation unit (gcc_references.c) accesses all of
// these through extern declarations and the Initial Exec TLS model.

_Thread_local int svar = 9000;
_Thread_local int szero;
_Thread_local int sarr[3];

void shivyc_set(int i, int v) {
  sarr[i] = v;
}

int shivyc_get(int i) {
  return sarr[i];
}

void shivyc_bump_zero() {
  szero = szero + 1;
}
