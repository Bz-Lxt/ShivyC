// Helper translation unit for storage_thread.c.
//
// Defines an external-linkage thread-local object accessed through the
// Initial Exec model from the main translation unit, and accesses (also
// through Initial Exec) a thread-local object defined there.

_Thread_local int ext_in_helper = 100;

void helper_inc_ext() {
  ext_in_helper = ext_in_helper + 1;
}

int helper_ext_value() {
  return ext_in_helper;
}

extern _Thread_local int ext_in_main;

void helper_double_main() {
  ext_in_main = ext_in_main * 2;
}
