#include <stdio.h>
#include <string.h>

#define BITS(S, f) do { \
    struct S _x; memset(&_x, 0, sizeof _x); _x.f = -1; \
    printf("%-4s.%-3s n=%zu:", #S, #f, sizeof(struct S)); \
    for (size_t _i = 0; _i < sizeof _x; _i++) \
        printf(" %02x", ((unsigned char*)&_x)[_i]); \
    printf("\n"); \
} while (0)

/* anonymous non-zero bitfields: alignment contribution? */
struct A1 { char a:1; int :10; };
struct A2 { char a:1; long :10; };
struct A3 { char a:1; int :10; char b:1; };
struct A4 { char a; int b:1; };
struct A5 { int a:30; int b:2; int x; };
struct A6 { int a:30; int b:3; int x; };
struct A7 { char c; int a:1; long l; };
struct A8 { int a:1; int b:1; int :0; short c:1; };
struct A9 { short x; int a:1; };
struct A10 { int a:1; const int b:2; };
struct A11 { unsigned long a:1; unsigned long b:63; };
struct A12 { char a:1; char :0; char b:1; };
struct A13 { signed char a:7; unsigned char b:7; };

int main(void) {
  printf("sizes A1=%zu A2=%zu A3=%zu\n", sizeof(struct A1),
         sizeof(struct A2), sizeof(struct A3));
  BITS(A3,b);
  BITS(A4,b);
  BITS(A5,a); BITS(A5,b); BITS(A5,x);
  BITS(A6,a); BITS(A6,b); BITS(A6,x);
  BITS(A7,a); BITS(A7,l);
  BITS(A8,c);
  BITS(A9,a);
  BITS(A11,a); BITS(A11,b);
  BITS(A12,a); BITS(A12,b);
  BITS(A13,a); BITS(A13,b);

  /* integer promotion of narrow bitfields */
  struct A13 z; memset(&z, 0, sizeof z);
  z.a = -1; z.b = -1;
  int pa = -z.a; unsigned int pb = -z.b;
  printf("promo signed char:7 -> %d ; unsigned char:7 -> %u\n", pa, pb);

  struct { unsigned int u:31; } t; t.u = 1;
  printf("unsigned int:31 neg=%d sizeof=%zu\n", -(int)t.u);

  struct { signed int s:3; } w; w.s = -1;
  printf("signed 3 read=%d\n", w.s);

  struct { unsigned int u:3; } v; v.u = -1;
  printf("unsigned 3 read=%u\n", v.u);

  /* long bitfields */
  struct { signed long l:40; } q; q.l = -1;
  printf("signed long 40 read=%ld\n", q.l + 0L);
  struct { unsigned long l:40; } q2; q2.l = -1;
  printf("unsigned long 40 read=%lu\n", q2.l + 0UL);
  return 0;
}
