#include <iostream>
#include <string>

struct Node {
    int value;
    Node* next;
    Node(int v) : value(v), next(nullptr) {}
};

class List {
    Node* head = nullptr;
    int size_ = 0;

public:
    ~List() {
        while (head) {
            Node* n = head;
            head = head->next;
            delete n;
        }
    }

    void pushFront(int v) {
        Node* n = new Node(v);
        n->next = head;
        head = n;
        size_++;
    }

    bool removeFirst(int v) {
        Node** cur = &head;
        while (*cur) {
            if ((*cur)->value == v) {
                Node* dead = *cur;
                *cur = dead->next;
                delete dead;
                size_--;
                return true;
            }
            cur = &(*cur)->next;
        }
        return false;
    }

    void reverse() {
        Node* prev = nullptr;
        while (head) {
            Node* next = head->next;
            head->next = prev;
            prev = head;
            head = next;
        }
        head = prev;
    }

    void print() const {
        for (Node* n = head; n; n = n->next) std::cout << n->value << ' ';
        std::cout << "(" << size_ << ")\n";
    }
};

int main() {
    List list;
    std::string cmd;
    int x;
    while (std::cin >> cmd >> x) {
        if (cmd == "push") list.pushFront(x);
        else if (cmd == "remove") std::cout << (list.removeFirst(x) ? "removed" : "missing") << "\n";
        else if (cmd == "reverse") list.reverse();
        list.print();
    }
    return 0;
}
