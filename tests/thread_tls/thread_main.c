// Multithreaded test for C11 _Thread_local.
//
// Four worker threads each mutate an external-linkage thread-local object
// (defined in thread_helper.c) directly and through helper functions, plus
// an internal-linkage thread-local object of this translation unit. This
// checks that every thread gets independent storage, while within a single
// thread both translation units see the same external object.

extern _Thread_local int shared_tls;
static _Thread_local int my_tls;

int results[4];
int params[4];

void helper_add(int v);
int helper_shared();

int pthread_create(unsigned long *t, void *attr,
                   void *(*start)(void *), void *arg);
int pthread_join(unsigned long t, void **retval);

void *worker(void *arg) {
  int id = *(int *)arg;
  int i;
  for (i = 0; i < 100; i++) {
    shared_tls = shared_tls + 1;
    helper_add(id);
    my_tls = my_tls + 3;
  }

  // shared_tls is 100 * (1 + id) in this thread, my_tls is 300, and
  // helper_shared() must observe the same shared_tls (cross-TU sharing).
  results[id] = shared_tls + my_tls + helper_shared();
  return 0;
}

int main() {
  unsigned long tids[4];
  int k;
  for (k = 0; k < 4; k++) {
    params[k] = k;
    if (pthread_create(&tids[k], 0, worker, &params[k])) return 50;
  }
  for (k = 0; k < 4; k++) {
    if (pthread_join(tids[k], 0)) return 51;
  }

  for (k = 0; k < 4; k++) {
    if (results[k] != 500 + 200 * k) return 60 + k;
  }

  // The main thread's TLS objects were never touched by the workers.
  if (helper_shared() != 0) return 70;
  if (my_tls != 0) return 71;

  return 0;
}
