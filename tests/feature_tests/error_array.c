int func(void);

struct S;

// error: array size must be compile-time constant
int gvlarr[func()];

// error: cannot have variable length array type as struct member
struct V { int arr[func()]; };
struct V vv;

int main() {
  int array[5];

  // error: expression on left of '=' is not assignable
  array = 4;

  // error: invalid operand types for array subscriping
  4[3];

  // error: invalid operand types for array subscriping
  array[array];

  // error: declared variable is not of assignable type
  int array1[5] = 1;

  void* p;
  // error: cannot subscript pointer to incomplete type
  p[4];

  // error: array size must be compile-time constant
  static int array1[func()];

  // error: array size must have integral type
  int array2[(int*)1];

  // error: array size must be positive
  int array3[-2];

  // error: array elements must have complete type
  struct S array4[3];

  // error: array elements must have complete type
  int array5[3][];

  int vlen = 3;
  // error: variable length array cannot be initialized
  int array6[vlen] = 3;
}
