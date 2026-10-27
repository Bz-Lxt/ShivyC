// Error tests for illegal uses of C11 _Thread_local.

// error: '_Thread_local' specified for function
_Thread_local int thread_func();

// error: '_Thread_local' cannot be used with 'typedef'
_Thread_local typedef int thread_int;

// error: storage class specified for function parameter
void param_func(_Thread_local int x) {}

// error: cannot have '_Thread_local' on struct member
struct S { _Thread_local int a; };

// error: cannot have '_Thread_local' on union member
union U { _Thread_local int b; };

int plain_x;
// error: thread-local declaration follows non-thread-local declaration of 'plain_x'
_Thread_local int plain_x;

_Thread_local int thread_y;
// error: non-thread-local declaration follows thread-local declaration of 'thread_y'
int thread_y;

int nonconstant(void);
// error: non-constant initializer for variable with static storage duration
_Thread_local int thread_nc = nonconstant();

int main() {
  // error: '_Thread_local' variable at block scope must be 'static' or 'extern'
  _Thread_local int block_tls;

  return 0;
}
