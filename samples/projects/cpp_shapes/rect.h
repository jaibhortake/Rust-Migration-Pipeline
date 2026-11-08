#pragma once
#include "shape.h"

class Rect : public Shape {
public:
    Rect(double w, double h);
    double area() const override;
    double perimeter() const override;
    std::string name() const override;
    bool isSquare() const;
private:
    double w_, h_;
};
