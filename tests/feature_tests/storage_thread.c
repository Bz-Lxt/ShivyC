// Feature tests for C11 _Thread_local objects.
//
// The corresponding storage_thread_helper.c defines some thread-local
// objects which are accessed here through extern declarations (the
// Initial Exec TLS model), and accesses other thread-local objects defined
// here (the Local Exec model) through helper functions.

extern _Thread_local int ext_in_helper;
void helper_inc_ext(void);
int helper_ext_value(void);
void helper_double_main(void);

_Thread_local int ext_in_main = 3;

static _Thread_local int local = 5;

_Thread_local int tentative_tls;

_Thread_local int tarr[4];

struct P { int x; int y; };
_Thread_local struct P tp;

int bump(int *p) {
  *p = *p + 1;
  return *p;
}

int twice(int v) {
  return v + v;
}

int main() {
  // External-linkage TLS defined in the other translation unit.
  if (ext_in_helper != 100) return 1;
  ext_in_helper = ext_in_helper + 1;
  if (helper_ext_value() != 101) return 2;
  helper_inc_ext();
  if (ext_in_helper != 102) return 3;
  if (bump(&ext_in_helper) != 103) return 4;

  // External-linkage TLS defined in this translation unit, modified in
  // the other one.
  if (ext_in_main != 3) return 5;
  helper_double_main();
  if (ext_in_main != 6) return 6;

  // Internal-linkage TLS.
  if (local != 5) return 7;
  local = local + 2;
  if (local != 7) return 8;

  // Tentative definition is zero-initialized.
  if (tentative_tls != 0) return 9;
  tentative_tls = 80;

  // Thread-local array with variable and constant indices.
  int i;
  for (i = 0; i < 4; i++) {
    tarr[i] = i * 4;
  }
  for (i = 0; i < 4; i++) {
    if (tarr[i] != i * 4) return 10 + i;
  }
  if (bump(&tarr[2]) != 9) return 14;
  if (twice(tarr[3]) != 24) return 15;

  // Thread-local struct, both members and addresses of members.
  tp.x = 1;
  tp.y = 2;
  bump(&tp.y);
  if (tp.x != 1) return 16;
  if (tp.y != 3) return 17;

  // Thread-local objects with block scope and static storage class.
  {
    static _Thread_local int b = 20;
    b = b + 1;
    if (b != 21) return 18;
  }
  {
    // This is a different object with a different scope.
    static _Thread_local int b = 20;
    if (b != 20) return 19;
  }

  // 103 + 6 + 7 + 80 + 0 + 4 + 9 + 12 + 1 + 3 = 225
  // Return: 225
  return (ext_in_helper + ext_in_main + local + tentative_tls
          + tarr[0] + tarr[1] + tarr[2] + tarr[3] + tp.x + tp.y);
}
