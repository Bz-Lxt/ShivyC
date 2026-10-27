// Helper translation unit for thread_main.c.

_Thread_local int shared_tls;

void helper_add(int v) {
  shared_tls = shared_tls + v;
}

int helper_shared() {
  return shared_tls;
}
