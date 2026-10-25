int climbStairs(int n) {
    long long a = 1, b = 1;
    for (int i = 0; i < n; i++) {
        long long t = a + b;
        a = b;
        b = t;
    }
    return (int)a;
}
