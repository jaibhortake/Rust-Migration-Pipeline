#include "circle.h"

static const double PI = 3.14159265358979323846;

Circle::Circle(double r) : r_(r) {}
double Circle::area() const { return PI * r_ * r_; }
double Circle::perimeter() const { return 2 * PI * r_; }
std::string Circle::name() const { return "circle"; }
