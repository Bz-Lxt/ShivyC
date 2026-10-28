#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Set field to all-ones (truncated to its width), dump raw struct bytes. */
#define BITS(S, f) do { \
    struct S _x; memset(&_x, 0, sizeof _x); _x.f = -1; \
    printf("%-4s.%-3s n=%zu:", #S, #f, sizeof(struct S)); \
    for (size_t _i = 0; _i < sizeof _x; _i++) \
        printf(" %02x", ((unsigned char*)&_x)[_i]); \
    printf("\n"); \
} while (0)

#define BITU(U, f) do { \
    union U _x; memset(&_x, 0, sizeof _x); _x.f = -1; \
    printf("%-4s.%-3s n=%zu:", #U, #f, sizeof(union U)); \
    for (size_t _i = 0; _i < sizeof _x; _i++) \
        printf(" %02x", ((unsigned char*)&_x)[_i]); \
    printf("\n"); \
} while (0)

struct S1 { int a:3; int b:5; int c:24; };
struct S2 { int a:3; int b:30; };
struct S3 { int a:3; int :0; int b:5; };
struct S4 { short a:5; int b:5; };
struct S5 { int a:5; short b; };
struct S6 { unsigned char a:1; unsigned char b:1; unsigned char c:1;
            unsigned char d:1; unsigned char e:1; unsigned char f:1;
            unsigned char g:1; unsigned char h:1; unsigned char i:1; };
struct S7 { unsigned short a:1; unsigned int b:1; };
struct S8 { int a:3; int :0; long b:3; };
struct S9 { int a:3; long b:3; };
struct S10 { char a:1; char b:1; int c:1; };
struct S11 { int a:3; int :5; int b:3; };
struct S12 { short a:10; short :0; short b:1; };
struct S13 { long a:40; long b:40; };
struct S14 { int a:1; char b; int c:1; };
struct S15 { unsigned a:31; unsigned b:31; unsigned c:2; };
struct S16 { _Bool a:1; _Bool b:1; };
struct S17 { int a:3; int :0; };
struct S18 { char a:1; int :0; char b:1; };
struct S19 { unsigned a:1; unsigned :0; unsigned b:1; unsigned :0; };
struct S20 { short :0; int a:1; };
struct S21 { int :0; };
struct S22 { int a:7; short :0; int b:1; };
struct S23 { int a:7; char :0; int b:1; };
struct S24 { long a:1; int b:1; };
struct S25 { int a:1; long :0; long b:1; };

union U1 { int a:3; int b:29; long c:40; };
union U2 { short a:1; int b:1; };

int main(void) {
  BITS(S1,a); BITS(S1,b); BITS(S1,c);
  BITS(S2,a); BITS(S2,b);
  BITS(S3,a); BITS(S3,b);
  BITS(S4,a); BITS(S4,b);
  BITS(S5,a); BITS(S5,b);
  BITS(S6,a); BITS(S6,i);
  BITS(S7,a); BITS(S7,b);
  BITS(S8,a); BITS(S8,b);
  BITS(S9,a); BITS(S9,b);
  BITS(S10,a); BITS(S10,b); BITS(S10,c);
  BITS(S11,a); BITS(S11,b);
  BITS(S12,a); BITS(S12,b);
  BITS(S13,a); BITS(S13,b);
  BITS(S14,a); BITS(S14,b); BITS(S14,c);
  BITS(S15,a); BITS(S15,b); BITS(S15,c);
  BITS(S16,a); BITS(S16,b);
  BITS(S18,a); BITS(S18,b);
  BITS(S20,a);
  BITS(S22,a); BITS(S22,b);
  BITS(S23,a); BITS(S23,b);
  BITS(S24,a); BITS(S24,b);
  BITS(S25,a); BITS(S25,b);
  printf("sizes: S17=%zu S19=%zu S21=%zu\n",
         sizeof(struct S17), sizeof(struct S19), sizeof(struct S21));
  BITU(U1,a); BITU(U1,b); BITU(U1,c);
  BITU(U2,a); BITU(U2,b);

  struct S1 s1; memset(&s1, 0xFF, sizeof s1);
  printf("signed s1 a=%d b=%d c=%d\n", s1.a, s1.b, s1.c);
  return 0;
}
