#pragma once
#include <cstddef>
#include <cstdlib>
#include <stdexcept>
#include <utility>
#include <type_traits>
#ifdef LFCB_DOUBLE
using Scalar=double;
#else
using Scalar=float;
#endif
inline const char* scalar_name(){return sizeof(Scalar)==8?"float64":"float32";}

struct Blob {
  void* data = nullptr;
  size_t bytes = 0;
  void (*release)(void*) = std::free;
  Blob() = default;
  Blob(void* p, size_t n, void (*d)(void*) = std::free): data(p),bytes(n),release(d) {}
  Blob(const Blob&) = delete;
  Blob& operator=(const Blob&) = delete;
  Blob(Blob&& o) noexcept: data(o.data),bytes(o.bytes),release(o.release) {o.data=nullptr;}
  ~Blob(){if(data)release(data);}
};
struct Shape {size_t z,y,x; size_t count()const{return z*y*x;}};
Blob compress_api(const Scalar* data, Shape shape, double tolerance);
Blob decompress_api(const Blob& compressed, Shape expected);
const char* codec_name();
inline void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
