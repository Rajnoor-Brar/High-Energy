#pragma once
#include <iostream>
#include <chrono>
#include <sys/ioctl.h>
#include <string>

void printProgressStat(int iEvent, int nEvents, int nDigits, std::string ETA){

    std::cout<<std::setfill(' ')<<"\033[2A\r"
                                <<"\t Events processed : "
                                  <<std::setw(nDigits)<<iEvent<<" out of "<< nEvents<<"  |  "
                                  <<std::setw(2)<<100*iEvent/nEvents<<"% \033[B\r"<<ETA<<"\033[B\r"<<std::flush;
}

std::string durationString(std::chrono::microseconds duration){
    using Seconds  = std::chrono::seconds;
    std::ostringstream durString;
    int totalSeconds = std::chrono::duration_cast<Seconds>(duration).count(),
        expectedSeconds = totalSeconds%60,
        expectedMinutes = (totalSeconds/60)%60,
        expectedHours   = (totalSeconds/3600)%24, 
        expectedDays    = totalSeconds/86400;

    durString<<(expectedDays ? std::to_string(expectedDays)+" day" + (expectedDays==1 ? " " : "s ") : "")
             <<(expectedHours ? std::to_string(expectedHours)+" hour"+ (expectedHours==1 ? " " : "s ") : "")
             <<(expectedMinutes ? std::to_string(expectedMinutes)+" minute"+ (expectedMinutes==1 ? " " : "s ") : "" )
             <<(expectedSeconds ? std::to_string(expectedSeconds)+" second"+ (expectedSeconds==1 ? " " : "s ") :
                (!(expectedDays|| expectedHours || expectedMinutes) ? " about now" : "") );

    return durString.str();
}
    
std::string updatedETA(int iEvent, int nEvents, std::chrono::microseconds duration){
    using SysClock = std::chrono::system_clock;

    if (nEvents < iEvent || iEvent <= 0) return std::string("ETA: --");

    double remainder = (nEvents - iEvent) / (double )iEvent;
    std::chrono::microseconds waitTime = std::chrono::duration_cast<std::chrono::microseconds>(remainder*duration);

    std::ostringstream ETA;

    time_t expectedTime = SysClock::to_time_t(SysClock::now() + waitTime);
    ETA<<"\033[2K\tETA : "<<std::put_time(std::localtime(&expectedTime), "%F %T ")
                    <<" in " <<durationString(waitTime);         
    return ETA.str();
}

void printProgressBar(double progress){
    static struct winsize w;
    ioctl(STDOUT_FILENO, TIOCGWINSZ, &w);
    static char done = '=';
    static char toDo = '-';
    
    int nCols = (int)w.ws_col ? ((int)w.ws_col)-6 : 100;
    int filledCols = (int)(progress*nCols);
    std::cout<<"\r\033[2K"<<"\033[32;1m|"<<std::string(filledCols,done)<<"\033[0m"<<">"<<"\033[31m"<<std::string(nCols-filledCols,toDo)<<"|\033[0m"<<std::flush;
}