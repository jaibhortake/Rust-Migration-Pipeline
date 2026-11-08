#pragma once
#include "shape.h"

class Circle : public Shape {
public:
    explicit Circle(double r);
    double area() const override;
    double perimeter() const override;
    std::string name() const override;
private:
    double r_;
};
