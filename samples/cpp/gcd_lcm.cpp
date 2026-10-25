#include <iostream>
using namespace std;

long long gcd(long long a, long long b) {
    while (b != 0) {
        long long t = a % b;
        a = b;
        b = t;
    }
    return a;
}

int main() {
    long long a, b;
    cin >> a >> b;
    long long g = gcd(a, b);
    cout << g << " " << (a / g) * b << endl;
    return 0;
}
