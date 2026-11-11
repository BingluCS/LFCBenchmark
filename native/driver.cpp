#include "adapter.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <vector>
#include <sched.h>

using Clock=std::chrono::steady_clock;
int main(int argc,char**argv){
 try {
  require(argc>=8,"usage: binary input z y x repetitions warmups alpha [alpha ...]");
  const Shape shape{std::stoull(argv[2]),std::stoull(argv[3]),std::stoull(argv[4])};
  const int reps=std::stoi(argv[5]), warmups=std::stoi(argv[6]);
  require(shape.x>0&&shape.y>0&&shape.z>0&&reps>0&&warmups>=0,"invalid dimensions or repetitions");
  const size_t n=shape.count(), raw_bytes=n*sizeof(float);
  std::ifstream file(argv[1],std::ios::binary|std::ios::ate);
  require(bool(file),"cannot open input file");
  require(size_t(file.tellg())==raw_bytes,"input byte count does not match shape");
  std::vector<float> input(n);file.seekg(0);file.read((char*)input.data(),raw_bytes);
  require(bool(file),"input read failed");
  double lo=std::numeric_limits<double>::infinity(),hi=-lo;
  for(float v:input){require(std::isfinite(v),"non-finite input");lo=std::min(lo,double(v));hi=std::max(hi,double(v));}
  const double range=hi-lo;require(range>0&&std::isfinite(range),"invalid or zero field range");
  std::cout<<std::setprecision(17);
  for(int k=7;k<argc;k++){
   const double alpha=std::stod(argv[k]), bound=range*alpha;
   require(alpha>0&&std::isfinite(bound)&&bound>0,"invalid bound");
   // PFPL ABS stores its tolerance in float32. Round DOWN for strict common-bound fairness.
   double effective=bound;
   if(std::string(codec_name())=="PFPL"){
    float f=float(bound);if(double(f)>bound)f=std::nextafter(f,0.0f);effective=double(f);
    require(effective>0,"PFPL tolerance underflow");
   }
   // SPERR reconstructs internally in double before its C API casts to float32.
   // Reserve one worst-case output ULP for that cast. At extremely tight bounds,
   // half the requested tolerance is conservative for rounding to an input grid.
   if(std::string(codec_name())=="SPERR"){
    const float m=float(std::max(std::abs(lo),std::abs(hi))+bound);
    const double ulp=double(std::nextafter(m,std::numeric_limits<float>::infinity()))-double(m);
    effective=bound>2*ulp?bound-ulp:bound*0.5;
   }
   for(int r=-warmups;r<reps;r++){
    std::vector<float> work(input); // outside the measured API call
    const auto c0=Clock::now(); auto encoded=compress_api(work.data(),shape,effective); const auto c1=Clock::now();
    require(encoded.data&&encoded.bytes,"empty compressed output");
    const bool input_modified=std::memcmp(work.data(),input.data(),raw_bytes)!=0;
    const auto d0=Clock::now(); auto decoded=decompress_api(encoded,shape); const auto d1=Clock::now();
    require(decoded.data&&decoded.bytes==raw_bytes,"decoded byte count mismatch");
    const float* reconstructed=(const float*)decoded.data;
    long double sumsq=0,bias=0;double max_error=0;size_t violations=0,nonfinite=0;
    for(size_t i=0;i<n;i++){
     if(!std::isfinite(reconstructed[i])){nonfinite++;continue;}
     const double e=double(reconstructed[i])-double(input[i]);
     max_error=std::max(max_error,std::abs(e));sumsq+=(long double)e*e;bias+=e;
     if(std::abs(e)>bound)violations++;
    }
    const double rmse=std::sqrt(double(sumsq/n));
    const double csec=std::chrono::duration<double>(c1-c0).count(),dsec=std::chrono::duration<double>(d1-d0).count();
    const bool good=!violations&&!nonfinite;
    std::cout<<"LFCB_RESULT {\"schema_version\":1,\"codec\":\""<<codec_name()<<"\",\"alpha\":"<<alpha
     <<",\"absolute_bound\":"<<bound<<",\"effective_bound\":"<<effective<<",\"range\":"<<range<<",\"min\":"<<lo<<",\"max\":"<<hi
     <<",\"warmup\":"<<(r<0?"true":"false")<<",\"repeat\":"<<(r+1)<<",\"elements\":"<<n
     <<",\"original_bytes\":"<<raw_bytes<<",\"compressed_bytes\":"<<encoded.bytes
     <<",\"ratio\":"<<double(raw_bytes)/encoded.bytes<<",\"bits_per_value\":"<<8.0*encoded.bytes/n
     <<",\"compress_seconds\":"<<csec<<",\"decompress_seconds\":"<<dsec
     <<",\"compress_MB_s\":"<<raw_bytes/1e6/csec<<",\"decompress_MB_s\":"<<raw_bytes/1e6/dsec
     <<",\"max_abs_error\":"<<max_error<<",\"rmse\":"<<rmse<<",\"nrmse\":"<<rmse/range
     <<",\"psnr_db\":";
    if(rmse>0)std::cout<<20*(std::log10(range)-std::log10(rmse));else std::cout<<"null";
    std::cout<<",\"mean_error\":"<<double(bias/n)<<",\"violations\":"<<violations<<",\"nonfinite\":"<<nonfinite
     <<",\"cpu\":"<<sched_getcpu()<<",\"encoder_modified_working_copy\":"<<(input_modified?"true":"false")<<",\"status\":\""<<(good?"ok":"violation")<<"\"}"<<std::endl;
   }
  }
  return 0;
 }catch(const std::exception&e){std::cerr<<"LFCB_ERROR "<<e.what()<<std::endl;return 2;}
}
