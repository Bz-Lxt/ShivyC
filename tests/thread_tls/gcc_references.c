// GCC-compiled translation unit which REFERENCES thread-local objects
// defined by ShivyC in shivyc_defines.c, and provides main().

extern _Thread_local int svar;
extern _Thread_local int szero;
extern _Thread_local int sarr[];

void shivyc_set(int, int);
int shivyc_get(int);
void shivyc_bump_zero(void);

int main(void) {
  if (svar != 9000) return 1;
  svar = 99;

  shivyc_set(0, 7);
  shivyc_set(1, 8);
  shivyc_set(2, 9);

  if (shivyc_get(0) != 7) return 2;
  if (shivyc_get(1) != 8) return 3;
  if (shivyc_get(2) != 9) return 4;

  if (sarr[0] != 7) return 5;
  if (sarr[2] != 9) return 6;

  if (szero != 0) return 7;
  shivyc_bump_zero();
  if (szero != 1) return 8;

  return 0;
}
