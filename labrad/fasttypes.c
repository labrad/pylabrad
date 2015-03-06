#include "Python.h"

/*
Currently supported: int, long, float, complex, string, bool, 1D lists, tuples, all dimensionless

Adding a type:
1- add clause to ft_create_type_string
2- check whether ft_type_strings_equivalent covers new type token
3- check whether ft_create_unambiguous_type_string covers new type token
4- add clause to ft_size, including #define for type size
5- add clause to ft_write_direct_to_buf
6- add clause to ft_write_reverse_to_buf

Future work, support:
import numpy as np
import labrad.units as U

fasttypes.flatten(4*U.ns) -> typetag: v[ns]
fasttypes.flatten((2+7j)*U.Unit('Volt')) -> typetag: c[ns]
fasttypes.flatten(np.eye(4)*U.GHz) -> typetag: *2v[GHz]
fasttypes.flatten(4*GHz*2*ns) -> typetag: v[]
*/

#define PyStringObject_SIZE (offsetof(PyStringObject, ob_sval) + 1)
#define FIXED_INT_SIZE 4
#define FIXED_LONG_SIZE 4
#define FIXED_FLOAT_SIZE 8
#define FIXED_COMPLEX_SIZE 16
#define FIXED_BOOL_SIZE 1
#define EXCEPTION_RAISED -1
#define TRUE 1
#define FALSE 0
#define BIG 1
#define LITTLE 0

// global variables (gv)
int ft_gv_initialized = FALSE;
int ft_gv_system_endianness = LITTLE;
PyObject *ft_gv_0 = NULL;
PyObject *ft_gv_1 = NULL;
PyObject *ft_gv_2 = NULL;
PyObject *ft_gv_long_num_bits = NULL;
PyObject *ft_gv_UINT_MAX = NULL;
PyObject *ft_gv_numpy = NULL;
PyObject *ft_gv_labrad_types = NULL;
PyObject *ft_gv_labrad_units = NULL;
PyTypeObject *ft_gv_labrad_units_WithUnit = NULL;
PyTypeObject *ft_gv_labrad_units_Value = NULL;
PyTypeObject *ft_gv_labrad_units_Complex = NULL;

// module initialization functions (called during first ft_flatten or ft_unflatten)
int ft_initialize();
int ft_system_supported();
void ft_detect_system_endianness();

// functions supporting ft_flatten
char *ft_append(char *str1, int *len1_ptr, char *str2, int len2);
char *ft_create_type_string(PyObject *o, int *len_ptr);
int ft_find_beginning_next_type_token(char *str, int i);
int ft_type_strings_equivalent(char *str1, int len1, char *str2, int len2);
char *ft_create_unambiguous_type_string(PyObject *o, int *len_ptr);
int ft_size(PyObject *o);
int ft_verify_long_ints_nonnegative(PyObject *o, char *str);
int ft_write_to_buf(PyObject *o, char *buf);
void ft_reverse_memcpy(void *dest, void *src, int len);
void ft_appropriate_memcpy(void *dest, void *src, int len);
PyObject *ft_create_empty_PyStringObject(int size);
PyObject *ft_flatten_no_parse(PyObject *o);
PyObject *ft_flatten(PyObject *self, PyObject *args);

// functions supporting ft_unflatten
// PyObject *ft_make_stuff(PyObject *self, PyObject *args);
PyObject *ft_build_Value(PyObject *o, char *t, int *ti_ptr);
PyObject *ft_unflatten_no_parse(char *s, int *si_ptr, char *t, int *ti_ptr);
PyObject *ft_unflatten_partial_parse(PyObject *o);
PyObject *ft_unflatten(PyObject *self, PyObject *args);

// test function: verifies o_i == unflatten(flatten(o_i)) for all o_i in [o_1, ..., o_n]
PyObject *ft_test(PyObject *self, PyObject *args);

// Q: what happens to module references when interpreter exits?
int ft_initialize() {
    PyObject *t;
    
    if (!ft_system_supported()) {
        PyErr_SetString(PyExc_AssertionError, "System has unsupported data type sizes.");
        return EXCEPTION_RAISED;
    }

    ft_detect_system_endianness();
    
    ft_gv_0 = PyInt_FromLong(0);
    ft_gv_1 = PyInt_FromLong(1);
    ft_gv_2 = PyInt_FromLong(2);
    ft_gv_long_num_bits = PyInt_FromLong(8*FIXED_LONG_SIZE);

    t = PyNumber_Power(ft_gv_2, ft_gv_long_num_bits, Py_None);
    ft_gv_UINT_MAX = PyNumber_Subtract(t, ft_gv_1);
    Py_DECREF(t);
    // PyObject_Print(ft_gv_UINT_MAX, stdout, Py_PRINT_RAW);
    
    ft_gv_numpy = PyImport_ImportModule("numpy");
    if (PyErr_Occurred() != NULL) goto exception;
    
    ft_gv_labrad_types = PyImport_ImportModule("labrad.types");
    if (PyErr_Occurred() != NULL) goto exception;

    ft_gv_labrad_units = PyImport_ImportModule("labrad.units");
    if (PyErr_Occurred() != NULL) goto exception;

    ft_gv_labrad_units_WithUnit = (PyTypeObject *)PyObject_GetAttrString(ft_gv_labrad_units, "WithUnit");
    if (PyErr_Occurred() != NULL) goto exception;
    
    ft_gv_labrad_units_Value = (PyTypeObject *)PyObject_GetAttrString(ft_gv_labrad_units, "Value");
    if (PyErr_Occurred() != NULL) goto exception;
    
    ft_gv_labrad_units_Complex = (PyTypeObject *)PyObject_GetAttrString(ft_gv_labrad_units, "Complex");
    if (PyErr_Occurred() != NULL) goto exception;
    
    ft_gv_initialized = TRUE;

    return TRUE;
    
exception:

    return EXCEPTION_RAISED;
}
 
int ft_system_supported() {
    if (sizeof(int) != FIXED_INT_SIZE ||
        sizeof(unsigned int) != FIXED_LONG_SIZE ||
        sizeof(double) != FIXED_FLOAT_SIZE ||
        2*sizeof(double) != FIXED_COMPLEX_SIZE ||
        sizeof(char) != FIXED_BOOL_SIZE)
        return FALSE;
    
    return TRUE;
}

void ft_detect_system_endianness() {
    int i = 1;
    char buf[FIXED_INT_SIZE];
    
    memcpy(buf, &i, FIXED_INT_SIZE);
    
    if (buf[0] == 0) ft_gv_system_endianness = BIG;
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
    PyObject *t, *t2;
    
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
    else if (PyBool_Check(o)) {
        str1 = ft_append(str1, &len1, "b", 1);
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
    else if (PyObject_TypeCheck(o, ft_gv_labrad_units_WithUnit)) {
        if (PyObject_TypeCheck(o, ft_gv_labrad_units_Value)) {
            // printf("Creating type token for Value\n");
            assert(str1 == NULL);
            str1 = ft_append(str1, &len1, "v[", 2);
        }
        else if (PyObject_TypeCheck(o, ft_gv_labrad_units_Complex)) {
            str1 = ft_append(str1, &len1, "c[", 2);
        }
        else {
            goto exception;
        }
        t = PyObject_GetAttrString(o, "unit");
        t2 = PyObject_GetAttrString(t, "name");
        str1 = ft_append(str1, &len1, ((PyStringObject *)t2)->ob_sval, PyString_GET_SIZE(t2));
        Py_DECREF(t2);
        Py_DECREF(t);
        str1 = ft_append(str1, &len1, "]", 1);
        // for (i=0; i<len1; i++) printf("%c", str1[i]);
    }
    else {
        goto exception;
    }

    *len_ptr = len1;
    return str1;
    
exception:

    printf("Serious fasttypes.c bug, detected in ft_create_type_string, likely located in ft_size. Unable to create type string for object that has passed ft_size.\n");
    assert(0);

    return NULL;
}

int ft_find_beginning_next_type_token(char *str, int i) {
    while (str[i] == '*') i++;
    
    if (str[i] == '(') {
        while (str[i] != ')') i++;
        i++;
    }
    else {
        if (str[i] == 'v' || str[i] == 'c') {
            while (str[i] != ']') i++;
            i++;
        }
        else i++;
    }
    
    return i;
}

int ft_type_strings_equivalent(char *str1, int len1, char *str2, int len2) {
    int i, j;
    
    // for (i=0; i<len2; i++) printf("%c", str2[i]);
    // printf("\n");
    
    i = j = 0;
    while (i < len1) {
        if (str1[i] == str2[j] || (str1[i] == 'w' && str2[j] == 'i')) {
            i++;
            j++;
        }
        else if (str2[j] != '?') {
            if (str1[i] == 'i' && str2[j] == 'w') {
                str1[i] = 'w';
            }
            else {
                return FALSE;
            }
        }
        else {
            j++;
            i = ft_find_beginning_next_type_token(str1, i);
        }
    }
    
    return TRUE;
}

char *ft_create_unambiguous_type_string(PyObject *o, int *len_ptr) {
    int i, j, n, len1, len2;
    char *str1, *str2;
    PyObject *t;
    
    len1 = len2 = 0;
    str1 = NULL;
    
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
            }
            if (i == n) {
                free(str1);
                *len_ptr = 0;
                PyErr_SetString(PyExc_TypeError, "Unable to infer a valid type string, too many empty lists.");
                goto exception;
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
                    goto exception;
                }
                free(str2);
            }
        }
    }
    else {
        // printf("no-list call\n");
        str1 = ft_create_type_string(o, &len1);
        for (j=0; j<len1; j++) {
            if (str1[j] == '?') str1[j] = 'i';
        }
    }
        
    *len_ptr = len1;
    return str1;
    
exception:

    return NULL;
}

// This function calculates the flattened size of a python object, and determines if it is built out of supported types.
int ft_size(PyObject *o) {
    int i, n, size = 0, val;
    PyObject *t;
    
    if (PyBool_Check(o)) {
        size = FIXED_BOOL_SIZE;
    }
    else if (PyInt_Check(o)) {
        size = FIXED_INT_SIZE;
    }
    else if (PyLong_Check(o)) {
        t = PyNumber_Subtract(o, ft_gv_UINT_MAX);
        if (PyObject_Compare(t, ft_gv_0) > 0) {
            PyErr_SetString(PyExc_TypeError, "Long integer greater than UINT_MAX.");
            goto exception;
        }
        Py_DECREF(t);
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
    else if (PyObject_TypeCheck(o, ft_gv_labrad_units_WithUnit)) {
        if (PyObject_TypeCheck(o, ft_gv_labrad_units_Value)) {
            size = FIXED_FLOAT_SIZE;
        }
        else if (PyObject_TypeCheck(o, ft_gv_labrad_units_Complex)) {
            size = FIXED_COMPLEX_SIZE;
        }
        else {
            PyErr_SetString(PyExc_TypeError, "Unsupported data type.");
            goto exception;
        }
    }
    else if (PyList_Check(o)) {
        size = FIXED_INT_SIZE;
        n = PyList_GET_SIZE(o);
        for (i=0; i<n; i++) {
            val = ft_size(PyList_GET_ITEM(o, i));
            if (val == EXCEPTION_RAISED) goto exception;
            size += val;
        }
    }
    else if (PyTuple_Check(o)) {
        size = FIXED_INT_SIZE;
        n = PyTuple_GET_SIZE(o);
        for (i=0; i<n; i++) {
            val = ft_size(PyTuple_GET_ITEM(o, i));
            if (val == EXCEPTION_RAISED) goto exception;
            size += val;
        }
    }
    else {
        PyErr_SetString(PyExc_TypeError, "Unsupported data type.");
        goto exception;
    }

    return size;
    
exception:

    return EXCEPTION_RAISED;
}

int ft_verify_long_ints_nonnegative(PyObject *o, char *str) {
    int i, j, n, flag;
    
    if (str[0] == 'w') {
        if (!PyInt_Check(o) && !PyLong_Check(o)) {
            PyErr_SetString(PyExc_TypeError, "Type string does not match data.");
            goto exception;
        }
        if (PyObject_Compare(o, ft_gv_0) < 0) {
            PyErr_SetString(PyExc_TypeError, "Long integer negative. Arrays of integers containing one or more value in [INT_MAX+1,UINT_MAX] must be all nonnegative.");
            goto exception;
        }
        return TRUE;
    }
    
    if (PyList_Check(o)) {
        n = PyList_GET_SIZE(o);
        for (i=0; i<n; i++) {
            flag = ft_verify_long_ints_nonnegative(PyList_GET_ITEM(o, i), str + 1);
            if (flag == EXCEPTION_RAISED) goto exception;
        }
        return TRUE;
    }
    
    if (PyTuple_Check(o)) {
        n = PyTuple_GET_SIZE(o);
        j = 1;
        for (i=0; i<n; i++) {
            flag = ft_verify_long_ints_nonnegative(PyTuple_GET_ITEM(o, i), str + j);
            if (flag == EXCEPTION_RAISED) goto exception;
            j = ft_find_beginning_next_type_token(str, j);
        }
        return TRUE;
    }
    
    return TRUE;
    
exception:

    return EXCEPTION_RAISED;
}

int ft_write_to_buf(PyObject *o, char *buf) {
    int i, n, size = 0;
    unsigned int w;
    double x;
    PyObject *t;
    
    if (PyBool_Check(o)) {
        size = FIXED_BOOL_SIZE;
        if (o == Py_True) *buf = 1;
        else *buf = 0;
    }
    else if (PyInt_Check(o)) {
        i = PyInt_AS_LONG(o);
        size = FIXED_INT_SIZE;
        ft_appropriate_memcpy(buf, &i, size);
    }
    else if (PyLong_Check(o)) {
        w = PyInt_AsUnsignedLongMask(o);
        size = FIXED_LONG_SIZE;
        ft_appropriate_memcpy(buf, &w, size);
    }
    else if (PyFloat_Check(o)) {
        x = PyFloat_AS_DOUBLE(o);
        size = FIXED_FLOAT_SIZE;
        ft_appropriate_memcpy(buf, &x, size);
    }
    else if (PyComplex_Check(o)) {
        x = PyComplex_RealAsDouble(o);
        ft_appropriate_memcpy(buf, &x, FIXED_FLOAT_SIZE);
        x = PyComplex_ImagAsDouble(o);
        ft_appropriate_memcpy(buf + FIXED_FLOAT_SIZE, &x, FIXED_FLOAT_SIZE);
        size = FIXED_COMPLEX_SIZE;
    }
    else if (PyString_Check(o)) {
        size = PyString_GET_SIZE(o);
        ft_appropriate_memcpy(buf, &size, FIXED_INT_SIZE);
        memcpy(buf + FIXED_INT_SIZE, ((PyStringObject *)o)->ob_sval, size);
        size += FIXED_INT_SIZE;
    }
    else if (PyObject_TypeCheck(o, ft_gv_labrad_units_WithUnit)) {
        t = PyObject_GetAttrString(o, "_value");
        if (PyObject_TypeCheck(o, ft_gv_labrad_units_Value)) {
            x = PyFloat_AS_DOUBLE(t);
            size = FIXED_FLOAT_SIZE;
            ft_appropriate_memcpy(buf, &x, size);
        }
        else if (PyObject_TypeCheck(o, ft_gv_labrad_units_Complex)) {
            x = PyComplex_RealAsDouble(t);
            ft_appropriate_memcpy(buf, &x, FIXED_FLOAT_SIZE);
            x = PyComplex_ImagAsDouble(t);
            ft_appropriate_memcpy(buf + FIXED_FLOAT_SIZE, &x, FIXED_FLOAT_SIZE);
            size = FIXED_COMPLEX_SIZE;
        }
        else {
            goto exception;
        }
        Py_DECREF(t);
    }
    else if (PyList_Check(o)) {
        n = PyList_GET_SIZE(o);
        // printf("list n: %d\n", n);
        ft_appropriate_memcpy(buf, &n, FIXED_INT_SIZE);
        size = FIXED_INT_SIZE;
        for (i=0; i<n; i++) {
            // printf("list i: %d\n", i);
            size += ft_write_to_buf(PyList_GET_ITEM(o, i), buf+size);
        }
    }
    else if (PyTuple_Check(o)) {
        n = PyTuple_GET_SIZE(o);
        // printf("tup n: %d\n", n);
        ft_appropriate_memcpy(buf, &n, FIXED_INT_SIZE);
        size = FIXED_INT_SIZE;
        for (i=0; i<n; i++) {
            // printf("tup i: %d\n", i);
            size += ft_write_to_buf(PyTuple_GET_ITEM(o, i), buf+size);
        }
    }
    else {
        goto exception;
    }

    // printf("size: %d\n", size);
    
    return size;
    
exception:

    printf("Serious fasttypes.c bug, detected in ft_write_to_buf, likely located in ft_size.\n");
    assert(0);

    return EXCEPTION_RAISED;
}

void ft_reverse_memcpy(void *dest, void *src, int len) {
    int i;
    char *cdest, *csrc;
    
    cdest = (char *)dest;
    csrc = (char *)src;
    
    for (i=0; i<len; i++) cdest[i] = csrc[len-1-i];
}

void ft_appropriate_memcpy(void *dest, void *src, int len) {
    if (ft_gv_system_endianness == LITTLE) ft_reverse_memcpy(dest, src, len);
    else memcpy(dest, src, len);
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

PyObject *ft_flatten_no_parse(PyObject *o) {
    // int i;
    int size, len;
    char *buf, *str;
    // double x;
    PyObject *tup;
    PyStringObject *so;
    
    str = NULL;
    tup = NULL;
    so = NULL;
    
    // printf("entered ft_flatten_no_parse\n");

    size = ft_size(o);
    // printf("size: %d\n", size);
    if (size == EXCEPTION_RAISED) goto exception;

    str = ft_create_unambiguous_type_string(o, &len);
    if (str == NULL) goto exception;
    // for (i=0; i<len; i++) printf("%c", str[i]);
    // printf("\n");
    
    if (strchr(str, 'w') != NULL) {
        if (ft_verify_long_ints_nonnegative(o, str) == EXCEPTION_RAISED) goto exception;
    }
    
    // Py_INCREF(Py_None);
    // return Py_None;
    
    tup = PyTuple_New(2);
    if (tup == NULL) goto exception;
    
    // so = (PyStringObject *)ft_create_empty_PyStringObject(size);
    so = (PyStringObject *)PyString_FromStringAndSize(NULL, size);
    if (so == NULL) goto exception;

    buf = so->ob_sval;
    // *** memory error likely in following line:
    ft_write_to_buf(o, buf);
    PyTuple_SET_ITEM(tup, 0, (PyObject *)so);
    
    // so = (PyStringObject *)ft_create_empty_PyStringObject(len);
    so = (PyStringObject *)PyString_FromStringAndSize(NULL, len);
    if (so == NULL) goto exception;

    buf = so->ob_sval;
    memcpy(buf, str, len);
    free(str);
    PyTuple_SET_ITEM(tup, 1, (PyObject *)so);
    
    return tup;
    
exception:
    
    if (str != NULL) free(str);
    
    if (tup != NULL) Py_DECREF(tup);
    else if (so != NULL) Py_DECREF(so);
    
    return NULL;
}

PyObject *ft_flatten(PyObject *self, PyObject *args) {
    PyObject *o;
    
    // Py_INCREF(Py_None);
    // return Py_None;
    
    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }
    
    PyArg_ParseTuple(args, "O", &o);
    if (PyErr_Occurred() != NULL) goto exception;
    
    return ft_flatten_no_parse(o);
    
exception:

    return NULL;
}

/*
PyObject *ft_make_stuff(PyObject *self, PyObject *args) {
    PyObject *o;
    
    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }

    PyArg_ParseTuple(args, "O", &o);
    if (PyObject_TypeCheck(o, ft_gv_labrad_units_Value)) printf("labRAD Value\n");
    
    return PyObject_CallMethod(ft_gv_numpy, "eye", "ii", 4, 4);

exception:

    return NULL;
}
*/

PyObject *ft_build_Value(PyObject *o, char *t, int *ti_ptr) {
    int n;
    PyObject *s;
    char *buf;

    n = 3;
    while (t[*ti_ptr + n] != ']') n++;
    n -= 2;
    s = PyString_FromStringAndSize(NULL, n);
    // if (s == NULL) goto exception;
    buf = ((PyStringObject *)s)->ob_sval;
    memcpy(buf, t + *ti_ptr + 2, n);
    
    return PyObject_CallMethod(ft_gv_labrad_types, "Value", "OO", o, s);
}

// function assumes computer does not run out of memory so all constructed objects are non NULL
PyObject *ft_unflatten_no_parse(char *s, int *si_ptr, char *t, int *ti_ptr) {
    int i, n, ti;
    double x, y;
    PyObject *o, *temp;
    char *buf, c;

    if (t[*ti_ptr] == '*') {
        // printf("unflat list\n");
        (*ti_ptr)++;
        ft_appropriate_memcpy(&n, s + *si_ptr, FIXED_INT_SIZE);
        *si_ptr += FIXED_INT_SIZE;
        o = PyList_New(n);
        for (i=0; i<n; i++) {
            // printf("list i: %d\n", i);
            PyList_SET_ITEM(o, i, ft_unflatten_no_parse(s, si_ptr, t, ti_ptr));
        }
    }
    else if (t[*ti_ptr] == '(') {
        // printf("unflat tup\n");
        ti = *ti_ptr;
        ti++;
        ft_appropriate_memcpy(&n, s + *si_ptr, FIXED_INT_SIZE);
        *si_ptr += FIXED_INT_SIZE;
        o = PyTuple_New(n);
        for (i=0; i<n; i++) {
            // printf("list i: %d\n", i);
            PyTuple_SET_ITEM(o, i, ft_unflatten_no_parse(s, si_ptr, t, &ti));
            ti = ft_find_beginning_next_type_token(t, ti);
        }
        // *ti_ptr = ft_find_beginning_next_type_token(t, *ti_ptr);
    }
    else if (t[*ti_ptr] == 'i') {
        ft_appropriate_memcpy(&n, s + *si_ptr, FIXED_INT_SIZE);
        *si_ptr += FIXED_INT_SIZE;
        o = PyInt_FromLong(n);
    }
    else if (t[*ti_ptr] == 'w') {
        ft_appropriate_memcpy(&n, s + *si_ptr, FIXED_INT_SIZE);
        *si_ptr += FIXED_INT_SIZE;
        o = PyInt_FromLong(n);
        if (PyObject_Compare(o, ft_gv_0) < 0) {
            temp = PyNumber_Add(o, ft_gv_UINT_MAX);
            Py_DECREF(o);
            o = temp;
            temp = PyNumber_Add(o, ft_gv_1);
            Py_DECREF(o);
            o = temp;
        }
    }
    else if (t[*ti_ptr] == 'v') {
        ft_appropriate_memcpy(&x, s + *si_ptr, FIXED_FLOAT_SIZE);
        *si_ptr += FIXED_FLOAT_SIZE;
        o = PyFloat_FromDouble(x);
        if (t[*ti_ptr + 2] != ']') {
            o = ft_build_Value(o, t, ti_ptr);
        }
    }
    else if (t[*ti_ptr] == 'c') {
        ft_appropriate_memcpy(&x, s + *si_ptr, FIXED_FLOAT_SIZE);
        *si_ptr += FIXED_FLOAT_SIZE;
        ft_appropriate_memcpy(&y, s + *si_ptr, FIXED_FLOAT_SIZE);
        *si_ptr += FIXED_FLOAT_SIZE;
        o = PyComplex_FromDoubles(x, y);
        if (t[*ti_ptr + 2] != ']') {
            o = ft_build_Value(o, t, ti_ptr);
        }
    }
    else if (t[*ti_ptr] == 's') {
        ft_appropriate_memcpy(&n, s + *si_ptr, FIXED_INT_SIZE);
        *si_ptr += FIXED_INT_SIZE;
        o = PyString_FromStringAndSize(NULL, n);
        // if (o == NULL) goto exception;
        buf = ((PyStringObject *)o)->ob_sval;
        memcpy(buf, s + *si_ptr, n);
        *si_ptr += n;
    }
    else if (t[*ti_ptr] == 'b') {
        ft_appropriate_memcpy(&c, s + *si_ptr, FIXED_BOOL_SIZE);
        *si_ptr += FIXED_BOOL_SIZE;
        o = PyBool_FromLong(c);
    }
     
    return o;
}

PyObject *ft_unflatten_partial_parse(PyObject *o) {
    int si, ti;
    PyStringObject *so, *to;
    char *s, *t;
    
    so = (PyStringObject *)PyTuple_GET_ITEM(o, 0);
    to = (PyStringObject *)PyTuple_GET_ITEM(o, 1);
    
    if (!PyString_Check(so) || !PyString_Check(to)) {
         PyErr_SetString(PyExc_TypeError, "unflatten() takes a tuple (string, string).");
         goto exception;
    }
    
    s = so->ob_sval;
    t = to->ob_sval;
    
    si = ti = 0;
    
    // PyObject_Print(so, stdout, Py_PRINT_RAW);
    // PyObject_Print(to, stdout, Py_PRINT_RAW);
    
    return ft_unflatten_no_parse(s, &si, t, &ti);
    
exception:
    
    return NULL;
}

PyObject *ft_unflatten(PyObject *self, PyObject *args) {
    PyObject *o;
    
    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }
    
    PyArg_ParseTuple(args, "O", &o);
    if (PyErr_Occurred() != NULL) goto exception;
    
    if (!PyTuple_Check(o) || PyTuple_GET_SIZE(o) != 2) {
         PyErr_SetString(PyExc_TypeError, "unflatten() takes a tuple (string, string).");
         goto exception;
    }
    
    return ft_unflatten_partial_parse(o);
    
exception:
    
    return NULL;
}

PyObject *ft_test(PyObject *self, PyObject *args) {
    int i, n, flag;
    PyObject *tc_mod, *tc_list, *tc_i, *tc_i_flat, *tc_i_unflat;

    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }

    tc_mod = PyImport_ImportModule("fasttypes_testcases");
    if (PyErr_Occurred() != NULL) goto exception;
    
    tc_list = PyObject_GetAttrString(tc_mod, "passcases");
    if (tc_list == NULL || !PyList_Check(tc_list)) goto exception;
    
    n = PyList_GET_SIZE(tc_list);
    flag = TRUE;
    for (i=0; i<n; i++) {
        tc_i = tc_i_flat = tc_i_unflat = NULL;
        printf("%d\n", i);
        tc_i = PyList_GET_ITEM(tc_list, i);
        if (tc_i != NULL) {
            PyObject_Print(tc_i, stdout, Py_PRINT_RAW);
            printf("\n");
            tc_i_flat = ft_flatten_no_parse(tc_i);
            if (tc_i_flat != NULL) {
                PyObject_Print(tc_i_flat, stdout, Py_PRINT_RAW);
                printf("\n");
                tc_i_unflat = ft_unflatten_partial_parse(tc_i_flat);
                if (tc_i_unflat != NULL) {
                    PyObject_Print(tc_i_unflat, stdout, Py_PRINT_RAW);
                    printf("\n");
                }
            }
        }
        
        if (tc_i_flat == NULL || tc_i_unflat == NULL || PyObject_Compare(tc_i, tc_i_unflat) != 0) {
            printf("ERROR: pass case %d failed\n", i);
            flag = FALSE;
        }
        printf("\n");

        if (tc_i_flat != NULL) Py_DECREF(tc_i_flat);
        if (tc_i_unflat != NULL) Py_DECREF(tc_i_unflat);
    }
    
    Py_DECREF(tc_list);
    
    tc_list = PyObject_GetAttrString(tc_mod, "failcases");
    if (tc_list == NULL || !PyList_Check(tc_list)) goto exception;
    
    n = PyList_GET_SIZE(tc_list);
    flag = TRUE;
    for (i=0; i<n; i++) {
        printf("%d\n", i);
        tc_i = PyList_GET_ITEM(tc_list, i);
        PyObject_Print(tc_i, stdout, Py_PRINT_RAW);
        printf("\n");
        tc_i_flat = ft_flatten_no_parse(tc_i);
        if (tc_i_flat != NULL) {
            printf("ERROR: fail case %d passed\n", i);
            flag = FALSE;
            Py_DECREF(tc_i_flat);
        }
        else {
            PyErr_Print();
        }
        printf("\n");
    }
    
    if (flag) printf("All test cases behaved as expected.\n");
    
    Py_DECREF(tc_list);
    Py_DECREF(tc_mod);
    
    Py_INCREF(Py_True);
    return Py_True;
    
exception:

    if (tc_list != NULL) Py_DECREF(tc_list);
    if (tc_mod != NULL) Py_DECREF(tc_mod);

    return NULL;
}

static PyMethodDef fasttypes_methods[] = {
    {"flatten", ft_flatten, METH_VARARGS, "flatten() doc string."},
    {"unflatten", ft_unflatten, METH_VARARGS, "unflatten() doc string."},
    {"test", ft_test, METH_VARARGS, "test() doc string."},
    {NULL, NULL}
};

PyMODINIT_FUNC initfasttypes(void) {
    Py_InitModule("fasttypes", fasttypes_methods);
}