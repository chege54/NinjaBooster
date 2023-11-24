#include "used.hpp"

int calc(int A, int B)
{
    StructFromUsedHpp S = {A, B};
    return S.A + S.B;
}
