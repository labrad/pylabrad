#include "Python.h"

/*
Currently supported: int, long, float, complex, string, bool, 1D lists, tuples, all dimensionless

Adding a type:
- add clause to ft_create_type_string
- check whether ft_type_strings_equivalent covers new type token
- check whether ft_create_unambiguous_type_string covers new type token
- add clause to ft_size, including #define for type size
- add clause to ft_write_direct_to_buf
- add clause to ft_write_reverse_to_buf
*/

#define PyStringObject_SIZE (offsetof(PyStringObject, ob_sval) + 1)
#define FIXED_INT_SIZE 4
#define FIXED_LONG_SIZE 4
#define FIXED_FLOAT_SIZE 8
#define FIXED_COMPLEX_SIZE 16
#define FIXED_BOOL_SIZE 1
#define UNSUPPORTED_PYTYPE -1
#define TRUE 1
#define FALSE 0
#define BIG 1
#define LITTLE 0

int system_endianness = LITTLE;

int ft_system_supported();
void detect_system_endianness();
char *ft_append(char *str1, int *len1_ptr, char *str2, int len2);
char *ft_create_type_string(PyObject *o, int *len_ptr);
char *ft_create_unambiguous_type_string(PyObject *o, int *len_ptr);
int ft_size(PyObject *o);
int ft_write_direct_to_buf(PyObject *o, char *buf);
void ft_reverse_memcpy(void *dest, void *src, int len);
int ft_write_reverse_to_buf(PyObject *o, char *buf);
PyObject *ft_create_empty_PyStringObject(int size);

static PyObject *ft_flatten(PyObject *self, PyObject *args);

int ft_system_supported() {
    if (sizeof(int) != FIXED_INT_SIZE ||
        sizeof(unsigned int) != FIXED_LONG_SIZE ||
        sizeof(double) != FIXED_FLOAT_SIZE ||
        2*sizeof(double) != FIXED_COMPLEX_SIZE ||
        sizeof(char) != FIXED_BOOL_SIZE)
        return FALSE;
    
    return TRUE;
}

void detect_system_endianness() {
    int i = 1;
    char buf[FIXED_INT_SIZE];
    
    memcpy(buf, &i, FIXED_INT_SIZE);
    
    if (buf[0] == 0) system_endianness = BIG;
}

char *ft_append(char *str1, int *len1_ptr, char *str2, int len2) {
    int total = *len1_ptr + len2;
    
    str1 = (char *)realloc(str1, total);
    memcpy(str1 + *len1_ptr, str2, len2);
    *len1_ptr = total;
    
    return str1;
}

char *ft_create_type_string(PyObject *o, int *len_ptr) {
    int i, n, len1, len2;
    char *str1, *str2;
    PyObject *t;
    
    len1 = len2 = 0;
    str1 = str2 = NULL;
    
    if (PyList_Check(o)) {
        str1 = ft_append(str1, &len1, "*", 1);
        if (PyList_GET_SIZE(o) == 0) {
            str1 = ft_append(str1, &len1, "?", 1);
        }
        else {
            o = PyList_GET_ITEM(o, 0);
            str2 = ft_create_type_string(o, &len2);
            str1 = ft_append(str1, &len1, str2, len2);
            free(str2);
        }
    }
    else if (PyTuple_Check(o)) {
        str1 = ft_append(str1, &len1, "(", 1);
        n = PyTuple_GET_SIZE(o);
        for (i=0; i<n; i++) {
            t = PyTuple_GET_ITEM(o, i);
            str2 = ft_create_type_string(t, &len2);
            str1 = ft_append(str1, &len1, str2, len2);
            free(str2);
            len2 = 0;
            str2 = NULL;
        }
        str1 = ft_append(str1, &len1, ")", 1);
    }
    else if (PyInt_Check(o)) {
        str1 = ft_append(str1, &len1, "i", 1);
    }
    else if (PyLong_Check(o)) {
        str1 = ft_append(str1, &len1, "w", 1);
    }
    else if (PyFloat_Check(o)) {
        str1 = ft_append(str1, &len1, "v[]", 3);
    }
    else if (PyComplex_Check(o)) {
        str1 = ft_append(str1, &len1, "c[]", 3);
    }
    else if (PyString_Check(o)) {
        str1 = ft_append(str1, &len1, "s", 1);
    }
    else if (PyBool_Check(o)) {
        str1 = ft_append(str1, &len1, "b", 1);
    }
    
    *len_ptr = len1;
    return str1;
}

int ft_type_strings_equivalent(char *str1, int len1, char *str2, int len2) {
    int i, j;
    
    i = j = 0;
    while (i < len1) {
        if (str1[i] == str2[j]) {
            i++;
            j++;
        }
        else if (str2[j] != '?') return FALSE;
        else {
            j++;
            while (str1[i] == '*') i++;
            if (str1[i] == '(') {
                while (str1[i] != ')') i++;
                i++;
            }
            else {
                if (str1[i] == 'v' || str1[i] == 'c') {
                    while (str1[i] != ']') i++;
                    i++;
                }
                else i++;
            }
        }
    }
    
    return TRUE;
}

char *ft_create_unambiguous_type_string(PyObject *o, int *len_ptr) {
    int i, j, n, len1, len2;
    char *str1, *str2;
    PyObject *t;
    
    len1 = len2 = 0;
    str1 = str2 = NULL;
    
    // printf("Entering ft_create_unambiguous_type_string\n");
    
    if (PyList_Check(o)) {
        str1 = ft_append(str1, &len1, "*", 1);
        if (PyList_GET_SIZE(o) == 0) {
            str1 = ft_append(str1, &len1, "i", 1);
        }
        else {
            n = PyList_GET_SIZE(o);
            for (i=0; i<n; i++) {
                t = PyList_GET_ITEM(o, i);
                str2 = ft_create_type_string(t, &len2);
                for (j=0; j<len2; j++) {
                    if (str2[j] == '?') break;
                }
                if (j == len2) {
                    str1 = ft_append(str1, &len1, str2, len2);
                    free(str2);
                    break;
                }
                free(str2);
                len2 = 0;
                str2 = NULL;
            }
            if (i == n) {
                free(str1);
                *len_ptr = 0;
                PyErr_SetString(PyExc_TypeError, "Unable to infer a valid type string, too many empty lists.");
                return NULL;
            }
            // for (i=0; i<len1; i++) printf("%c", str1[i]);
            // printf("\n");
            for (i=0; i<n; i++) {
                t = PyList_GET_ITEM(o, i);
                str2 = ft_create_type_string(t, &len2);
                if (!ft_type_strings_equivalent(str1+1, len1-1, str2, len2)) {
                    free(str1);
                    free(str2);
                    *len_ptr = 0;
                    PyErr_SetString(PyExc_TypeError, "Unable to infer a valid type string, inhomogeneous list.");
                    return NULL;
                }
            }
        }
    }
    else {
        str1 = ft_create_type_string(o, &len1);
        for (j=0; j<len1; j++) {
            if (str1[j] = '?') str1[j] = 'i';
        }
    }
        
    *len_ptr = len1;
    return str1;
}

// This function calculates the flattened size of a python object, and determines if it is built out of supported types.
int ft_size(PyObject *o) {
    int i, n, size = 0, val;
    
    if (PyInt_Check(o)) {
        size = FIXED_INT_SIZE;
    }
    else if (PyLong_Check(o)) {
        size = FIXED_LONG_SIZE;
    }
    else if (PyFloat_Check(o)) {
        size = FIXED_FLOAT_SIZE;
    }
    else if (PyComplex_Check(o)) {
        size = FIXED_COMPLEX_SIZE;
    }
    else if (PyString_Check(o)) {
        size = FIXED_INT_SIZE + PyString_GET_SIZE(o);
    }
    else if (PyBool_Check(o)) {
        size = FIXED_BOOL_SIZE;
    }
    else if (PyList_Check(o)) {
        size += FIXED_INT_SIZE;
        n = PyList_GET_SIZE(o);
        for (i=0; i<n; i++) {
            val = ft_size(PyList_GET_ITEM(o, i));
            if (val == UNSUPPORTED_PYTYPE) return val;
            size += val;
        }
    }
    else if (PyTuple_Check(o)) {
        n = PyTuple_GET_SIZE(o);
        for (i=0; i<n; i++) {
            val = ft_size(PyTuple_GET_ITEM(o, i));
            if (val == UNSUPPORTED_PYTYPE) return val;
            size += val;
        }
    }
    else {
        return UNSUPPORTED_PYTYPE;
    }

    return size;
}

int ft_write_direct_to_buf(PyObject *o, char *buf) {
    int i, n, size = 0;
    unsigned int w;
    double x;
    
    if (PyInt_Check(o)) {
        i = PyInt_AS_LONG(o);
        size = FIXED_INT_SIZE;
        memcpy(buf, &i, size);
    }
    else if (PyLong_Check(o)) {
        w = PyInt_AS_LONG(o);
        size = FIXED_LONG_SIZE;
        memcpy(buf, &w, size);
    }
    else if (PyFloat_Check(o)) {
        x = PyFloat_AS_DOUBLE(o);
        size = FIXED_FLOAT_SIZE;
        memcpy(buf, &x, size);
    }
    else if (PyComplex_Check(o)) {
        x = PyComplex_RealAsDouble(o);
        memcpy(buf, &x, FIXED_FLOAT_SIZE);
        x = PyComplex_ImagAsDouble(o);
        memcpy(buf, &x, FIXED_FLOAT_SIZE);
        size = FIXED_COMPLEX_SIZE;
    }
    else if (PyString_Check(o)) {
        size = PyString_GET_SIZE(o);
        memcpy(buf, &size, FIXED_INT_SIZE);
        memcpy(buf + FIXED_INT_SIZE, ((PyStringObject *)o)->ob_sval, size);
        size += FIXED_INT_SIZE;
    }
    else if (PyBool_Check(o)) {
        size = FIXED_BOOL_SIZE;
        if (o == Py_True) *buf = 1;
        else *buf = 0;
    }
    else if (PyList_Check(o)) {
        n = PyList_GET_SIZE(o);
        memcpy(buf, &n, FIXED_INT_SIZE);
        size += FIXED_INT_SIZE;
        for (i=0; i<n; i++) {
            size += ft_write_direct_to_buf(PyList_GET_ITEM(o, i), buf+size);
        }
    }
    else if (PyTuple_Check(o)) {
        n = PyTuple_GET_SIZE(o);
        for (i=0; i<n; i++) {
            size += ft_write_direct_to_buf(PyTuple_GET_ITEM(o, i), buf+size);
        }
    }

    return size;
}

void ft_reverse_memcpy(void *dest, void *src, int len) {
    int i;
    char *cdest, *csrc;
    
    cdest = (char *)dest;
    csrc = (char *)src;
    
    for (i=0; i<len; i++) cdest[i] = csrc[len-1-i];
}

int ft_write_reverse_to_buf(PyObject *o, char *buf) {
    int i, n, size = 0;
    unsigned int w;
    double x;
    
    if (PyInt_Check(o)) {
        i = PyInt_AS_LONG(o);
        size = FIXED_INT_SIZE;
        ft_reverse_memcpy(buf, &i, size);
    }
    else if (PyLong_Check(o)) {
        w = PyInt_AS_LONG(o);
        size = FIXED_LONG_SIZE;
        ft_reverse_memcpy(buf, &w, size);
    }
    else if (PyFloat_Check(o)) {
        x = PyFloat_AS_DOUBLE(o);
        size = FIXED_FLOAT_SIZE;
        ft_reverse_memcpy(buf, &x, size);
    }
    else if (PyComplex_Check(o)) {
        x = PyComplex_RealAsDouble(o);
        ft_reverse_memcpy(buf, &x, FIXED_FLOAT_SIZE);
        x = PyComplex_ImagAsDouble(o);
        ft_reverse_memcpy(buf, &x, FIXED_FLOAT_SIZE);
        size = FIXED_COMPLEX_SIZE;
    }
    else if (PyString_Check(o)) {
        size = PyString_GET_SIZE(o);
        ft_reverse_memcpy(buf, &size, FIXED_INT_SIZE);
        memcpy(buf + FIXED_INT_SIZE, ((PyStringObject *)o)->ob_sval, size);
        size += FIXED_INT_SIZE;
    }
    else if (PyBool_Check(o)) {
        size = FIXED_BOOL_SIZE;
        if (o == Py_True) *buf = 1;
        else *buf = 0;
    }
    else if (PyList_Check(o)) {
        n = PyList_GET_SIZE(o);
        ft_reverse_memcpy(buf, &n, FIXED_INT_SIZE);
        size += FIXED_INT_SIZE;
        for (i=0; i<n; i++) {
            size += ft_write_reverse_to_buf(PyList_GET_ITEM(o, i), buf+size);
        }
    }
    else if (PyTuple_Check(o)) {
        n = PyTuple_GET_SIZE(o);
        for (i=0; i<n; i++) {
            size += ft_write_reverse_to_buf(PyTuple_GET_ITEM(o, i), buf+size);
        }
    }

    return size;
}

PyObject *ft_create_empty_PyStringObject(int size) {
    PyStringObject *so;

    so = (PyStringObject *)PyObject_MALLOC(PyStringObject_SIZE + size);

    if (so == NULL) {
        PyErr_SetString(PyExc_MemoryError, "Out of memory.");
        return NULL;
    }

    PyObject_INIT_VAR(so, &PyString_Type, size);
    so->ob_shash = -1;
    so->ob_sstate = SSTATE_NOT_INTERNED;
    so->ob_sval[size] = '\0';

    return (PyObject *)so;
}

static PyObject *ft_flatten(PyObject *self, PyObject *args) {
    int i, ok, size, len = 0;
    char *buf, *str;
    PyObject *o = NULL, *tup;
    PyStringObject *so;
    
    if (!ft_system_supported()) {
        PyErr_SetString(PyExc_AssertionError, "System has unsupported data type sizes.");
        return NULL;
    }
    detect_system_endianness();
    
    ok = PyArg_ParseTuple(args, "O", &o);
    if (ok != 1) {
        PyErr_SetString(PyExc_SyntaxError, "Incorrect number of arguments.");
        return NULL;
    }
    
    if (o == NULL) {
        PyErr_SetString(PyExc_SyntaxError, "Incorrect number of arguments.");
        return NULL;
    }
    
    size = ft_size(o);
    if (size == UNSUPPORTED_PYTYPE) {
        PyErr_SetString(PyExc_TypeError, "Unsupported Python object type.");
        return NULL;
    }
    // printf("size: %d\n", size);

    str = ft_create_unambiguous_type_string(o, &len);
    if (str == NULL) return NULL;
    // for (i=0; i<len; i++) printf("%c", str[i]);
    // printf("\n");
    
    tup = PyTuple_New(2);
    
    so = (PyStringObject *)ft_create_empty_PyStringObject(size);
    buf = so->ob_sval;
    if (system_endianness == BIG) {
        if (ft_write_direct_to_buf(o, buf) != size) {
            PyErr_SetString(PyExc_Exception, "Error occurred during flattening.");
            return NULL;
        }
    }
    else {
        if (ft_write_reverse_to_buf(o, buf) != size) {
            PyErr_SetString(PyExc_Exception, "Error occurred during flattening.");
            return NULL;
        }
    }
    PyTuple_SET_ITEM(tup, 0, (PyObject *)so);
    
    so = (PyStringObject *)ft_create_empty_PyStringObject(len);
    buf = so->ob_sval;
    memcpy(buf, str, len);
    free(str);
    PyTuple_SET_ITEM(tup, 1, (PyObject *)so);
    
    return tup;
}

static PyMethodDef fasttypes_methods[] = {
    {"flatten", ft_flatten, METH_VARARGS, "flatten() doc string."},
    {NULL, NULL}
};

PyMODINIT_FUNC initfasttypes(void) {
    Py_InitModule("fasttypes", fasttypes_methods);
}