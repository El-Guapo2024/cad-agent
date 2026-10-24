/* A malloc that never reuses memory, preloaded into freecadcmd by make.py.
 *
 * PlaneGCS orders a subsystem's unknowns by their addresses (std::set<double*>), and the Sketcher
 * allocates each with new, so on an under-constrained sketch FreeCAD's answer depends on what the
 * heap hands out: two runs of the same script disagree on about a third of make.py's cases. With
 * every allocation above the one before, the parameters are ordered as they are made, which is the
 * order the port (ui/planegcs/sketch.cpp, Sketch::newParam) uses, and FreeCAD is repeatable.
 *
 *     cc -O2 -shared -fPIC -o bump_malloc.so bump_malloc.c
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>

#define ARENA ((size_t)1 << 36) /* 64 GiB of address space, touched only as used */

static char* volatile base;
static size_t used; /* updated atomically: FreeCAD runs its QR diagnoses on other threads */

static void* bump(size_t size, size_t align)
{
    if (!base) {
        char* b = mmap(NULL, ARENA, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
        if (b == MAP_FAILED) {
            return NULL;
        }
        char* expected = NULL;
        if (!__atomic_compare_exchange_n(&base, &expected, b, 0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) {
            munmap(b, ARENA);
        }
    }
    if (align < 16) {
        align = 16;
    }
    /* a header in front of each block keeps its size, for realloc */
    size_t old = __atomic_load_n(&used, __ATOMIC_SEQ_CST), start;
    do {
        start = (old + sizeof(size_t) + align - 1) & ~(align - 1);
        if (start + size > ARENA) {
            errno = ENOMEM;
            return NULL;
        }
    } while (!__atomic_compare_exchange_n(&used, &old, start + size, 0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST));
    ((size_t*)(base + start))[-1] = size;
    return base + start;
}

void* malloc(size_t size) { return bump(size, 16); }
void free(void* p) { (void)p; }
void* calloc(size_t n, size_t size) { return bump(n * size, 16); } /* fresh pages are zero */
void* realloc(void* p, size_t size)
{
    void* q = bump(size, 16);
    if (p && q) {
        size_t old = ((size_t*)p)[-1];
        memcpy(q, p, old < size ? old : size);
    }
    return q;
}
void* memalign(size_t align, size_t size) { return bump(size, align); }
void* aligned_alloc(size_t align, size_t size) { return bump(size, align); }
void* valloc(size_t size) { return bump(size, 4096); }
void* pvalloc(size_t size) { return bump((size + 4095) & ~(size_t)4095, 4096); }
int posix_memalign(void** out, size_t align, size_t size)
{
    void* p = bump(size, align);
    if (!p) {
        return ENOMEM;
    }
    *out = p;
    return 0;
}
size_t malloc_usable_size(void* p) { return p ? ((size_t*)p)[-1] : 0; }
