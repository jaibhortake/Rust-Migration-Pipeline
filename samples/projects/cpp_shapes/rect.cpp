#include "rect.h"

Rect::Rect(double w, double h) : w_(w), h_(h) {}
double Rect::area() const { return w_ * h_; }
double Rect::perimeter() const { return 2 * (w_ + h_); }
std::string Rect::name() const { return isSquare() ? "square" : "rect"; }
bool Rect::isSquare() const { return w_ == h_; }
