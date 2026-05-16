#pragma once
#include <chrono>
#include <iostream>
#include <fstream>
#include <string>

class BlockTimer {
    public:
        explicit BlockTimer(std::string name)
            : name_(std::move(name)),
            start_(std::chrono::steady_clock::now()),
            stream("output/timer.log", std::ios::app) {}

        ~BlockTimer() {
            auto end = std::chrono::steady_clock::now();

            double ms = std::chrono::duration<double, std::milli>(end - start_).count();
            stream << ms<<"\n";
        }

    private:
        std::ofstream stream;
        std::string name_;
        std::chrono::steady_clock::time_point start_;
};