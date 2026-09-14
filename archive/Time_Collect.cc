#include <iostream>
#include <fstream>
#include <string>

int main(){
    std::fstream stream("output/timer.log", std::ios::in);
    double ms = 0;
    double total = 0;
    while(stream >> ms){
        total += ms;
    }
    std::cout << "Total time: " << total/1000/60 << " min" << std::endl;
    return 0;
}