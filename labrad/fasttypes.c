#include "Python.h"

/*
NOTES:
- Python.h modifies assert() so it does not trigger program termination on failure. exit() terminates the interpreter.
- small memory allocations assumed to work.
- ndarrays not allowed to contain objects with structure.

Common brief variable names and meanings
i : for loop counter
lobj : list Python object
n : the length of a list/tuple/array/string/etc object
obj : generic Python object
robj : the Python object that will be returned by a function
sobj : string Python object
tobj : temporary Python object
*/

#define TRUE 1
#define FALSE 0
#define SUCCESS 1
#define EXCEPTION_RAISED -1
#define BIG_ENDIAN ">"
#define LITTLE_ENDIAN "<"

#define LABRAD_BOOL_SIZE 1
#define LABRAD_INT_SIZE 4
#define LABRAD_LONG_SIZE 8
#define LABRAD_FLOAT_SIZE 8

#define EMPTY 0
#define BOOL 1
#define UINT31 2
#define INT32 3
#define UINT32 4
#define FLOAT64 5
#define COMPLEX128 6
#define FLOAT64_SU 7
#define COMPLEX128_SU 8
#define STRING 9
#define CLUSTER 10
#define LIST 11
#define NDARRAY 12
#define NDARRAY_SU 13
#define TIME 14
#define ERROR 15

typedef struct cobj COBJ;

struct cobj {
    int type; // type of this cobj
    int subtype; // if ndarray, type of each element in array, if error, specific type of error
    int i; // good for BOOL, UINT31, INT32
    unsigned int n; // good for UINT32, length cobj_arr, length str, length dim_arr
    double x, y; // float and complex data
    char *str; // string, unit, and error data
    COBJ **cobj_arr; // sub cojbs contained in cluster or list
    unsigned int *dim_arr; // dimensions of ndarray
    void *arr; // data of ndarray
    long long int secs, usecs; // time data
};

int ft_gv_initialized = FALSE;
int ft_gv_system_big_endian = FALSE;
int ft_gv_send_big_endian = TRUE;
PyObject *ft_gv_0 = NULL;
PyObject *ft_gv_1 = NULL;
PyObject *ft_gv_2 = NULL;
PyObject *ft_gv_int_num_bits = NULL;
PyObject *ft_gv_int_num_bits_minus_1 = NULL;
PyObject *ft_gv_INT_MIN = NULL;
PyObject *ft_gv_INT_MAX = NULL;
PyObject *ft_gv_UINT_MAX = NULL;
PyObject *ft_gv_numpy = NULL;
PyTypeObject *ft_gv_numpy_ndarray = NULL;
PyObject *ft_gv_labrad_types = NULL;
PyObject *ft_gv_labrad_units = NULL;
PyTypeObject *ft_gv_labrad_units_WithUnit = NULL;
PyTypeObject *ft_gv_labrad_units_Value = NULL;
PyTypeObject *ft_gv_labrad_units_Complex = NULL;
PyTypeObject *ft_gv_labrad_units_ValueArray = NULL;

PyObject *ft_flatten(PyObject *self, PyObject *args, PyObject *keywds);
COBJ *ft_create_cobj_from_pyobj(PyObject *obj);
COBJ *ft_create_empty_from_pynone(PyObject *obj);
COBJ *ft_create_bool_from_pybool(PyObject *obj);
COBJ *ft_create_cobj_from_pyint_or_pylong(PyObject *obj);
COBJ *ft_create_float_from_pyfloat(PyObject *obj);
COBJ *ft_create_complex_from_pycomplex(PyObject *obj);
COBJ *ft_create_cobj_from_pyWithUnit(PyObject *obj);

int ft_initialize();
int ft_system_supported();
void ft_detect_system_endianness();
int ft_set_send_endianness(PyObject *endianness);

COBJ *ft_allocate_memory_for_cobj();
void ft_print_cobj(COBJ *cobj);
void ft_free_cobj(COBJ *cobj);
char *ft_get_unit_string(PyObject *obj);
COBJ *ft_convert_to_standard_units(COBJ *cobj);

PyObject *ft_test(PyObject *self, PyObject *args);

PyObject *ft_flatten(PyObject *self, PyObject *args, PyObject *keywds) {
    // int i, n;
    PyObject *obj, *types, *endianness, *sobj, *lobj/*, *robj*/;
    char *kwlist[] = {"obj", "types", "endianness", NULL};
    COBJ *cobj;
    
    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }
    
    obj = types = endianness = sobj = lobj = NULL;
    
    if (!PyArg_ParseTupleAndKeywords(args, keywds, "O|OO", kwlist, &obj, &types, &endianness)) goto exception;
    
    if (endianness != NULL) {
        if (ft_set_send_endianness(endianness) == EXCEPTION_RAISED) goto exception;
    }
    
    if (types == NULL) {
        types = sobj = PyString_FromString("?");
    }
    if (!PyList_Check(types)) {
        lobj = PyList_New(1);
        if (sobj == NULL) Py_INCREF(types);
        PyList_SET_ITEM(lobj, 0, types);
        types = lobj;
    }
    
    cobj = ft_create_cobj_from_pyobj(obj);
    if (cobj == NULL) goto exception;
    ft_print_cobj(cobj);
    
    // temporarily just clean up
    ft_free_cobj(cobj);
    if (lobj != NULL) Py_DECREF(lobj);
    
    Py_INCREF(Py_None);
    return Py_None;
    // -------------------------

exception:
    
    if (lobj != NULL) Py_DECREF(lobj);
    
    return NULL;
}

COBJ *ft_create_cobj_from_pyobj(PyObject *obj) {
    COBJ *cobj;
    
    cobj = NULL;
    
    if (obj == Py_None) {
        cobj = ft_create_empty_from_pynone(obj);
    }
    else if (PyBool_Check(obj)) {
        cobj = ft_create_bool_from_pybool(obj);
    }
    else if (PyInt_Check(obj) || PyLong_Check(obj)) {
        cobj = ft_create_cobj_from_pyint_or_pylong(obj);
        if (cobj == NULL) goto exception;
    }
    else if (PyFloat_Check(obj)) {
        cobj = ft_create_float_from_pyfloat(obj);
    }
    else if (PyComplex_Check(obj)) {
        cobj = ft_create_complex_from_pycomplex(obj);
    }
    else if (PyObject_TypeCheck(obj, ft_gv_labrad_units_WithUnit)) {
        cobj = ft_create_cobj_from_pyWithUnit(obj);
    }
    
    if (cobj == NULL) {
        PyErr_SetString(PyExc_TypeError, "unsupported python object");
        goto exception;
    }
    
    return cobj;
    
exception:
    
    return NULL;
}

COBJ *ft_create_empty_from_pynone(PyObject *obj) {
    COBJ *cobj;
    
    cobj = ft_allocate_memory_for_cobj();
    
    cobj->type = EMPTY;
    
    return cobj;
}

COBJ *ft_create_bool_from_pybool(PyObject *obj) {
    COBJ *cobj;
    
    cobj = ft_allocate_memory_for_cobj();
    
    cobj->type = BOOL;
    
    if (obj == Py_True) cobj->i = TRUE;
    else cobj->i = FALSE;
    
    return cobj;
}

COBJ *ft_create_cobj_from_pyint_or_pylong(PyObject *obj) {
    COBJ *cobj;
    
    cobj = ft_allocate_memory_for_cobj();
    
    if (PyObject_Compare(obj, ft_gv_0) < 0) {
        if (PyObject_Compare(obj, ft_gv_INT_MIN) < 0) {
            cobj->type = FLOAT64;
            cobj->x = PyLong_AsDouble(obj);
            if (PyErr_Occurred() != NULL) goto exception;
        }
        else {
            cobj->type = INT32;
            cobj->i = (int)PyInt_AS_LONG(obj);
        }
    }
    else if (PyObject_Compare(obj, ft_gv_UINT_MAX) > 0) {
        cobj->type = FLOAT64;
        cobj->x = PyLong_AsDouble(obj);
        if (PyErr_Occurred() != NULL) goto exception;
    }
    else if (PyObject_Compare(obj, ft_gv_INT_MAX) > 0) {
        cobj->type = UINT32;
        cobj->n = (unsigned int)PyInt_AS_LONG(obj);
    }
    else {
        cobj->type = UINT31;
        cobj->i = (int)PyInt_AS_LONG(obj);
    }
    
    return cobj;
    
exception:
    
    ft_free_cobj(cobj);
    
    return NULL;
}

COBJ *ft_create_float_from_pyfloat(PyObject *obj) {
    COBJ *cobj;
    
    cobj = ft_allocate_memory_for_cobj();
    
    cobj->type = FLOAT64;
    cobj->x = PyFloat_AS_DOUBLE(obj);
    
    return cobj;
}

COBJ *ft_create_complex_from_pycomplex(PyObject *obj) {
    COBJ *cobj;
    
    cobj = ft_allocate_memory_for_cobj();
    
    cobj->type = COMPLEX128;
    cobj->x = PyComplex_RealAsDouble(obj);
    cobj->y = PyComplex_ImagAsDouble(obj);
    
    return cobj;
}

COBJ *ft_create_cobj_from_pyWithUnit(PyObject *obj) {
    PyObject *tobj;
    COBJ *cobj;

    tobj = PyObject_GetAttrString(obj, "_value");
    cobj = ft_create_cobj_from_pyobj(tobj);
    Py_DECREF(tobj);
    if (cobj == NULL) goto exception;

    cobj->str = ft_get_unit_string(obj);
    cobj->n = strlen(cobj->str);
    cobj = ft_convert_to_standard_units(cobj);
    if (cobj == NULL) goto exception;
    
    return cobj;
    
exception:
    
    return NULL;
}

int ft_initialize() {
    PyObject *tobj;
    
    if (!ft_system_supported()) {
        PyErr_SetString(PyExc_AssertionError, "system has unsupported data type sizes");
        goto exception;
    }

    ft_detect_system_endianness();
    
    ft_gv_0 = PyInt_FromLong(0);
    ft_gv_1 = PyInt_FromLong(1);
    ft_gv_2 = PyInt_FromLong(2);
    ft_gv_int_num_bits = PyInt_FromLong(8*LABRAD_INT_SIZE);
    ft_gv_int_num_bits_minus_1 = PyInt_FromLong(8*LABRAD_INT_SIZE-1);
    
    tobj = PyNumber_Power(ft_gv_2, ft_gv_int_num_bits, Py_None);
    ft_gv_UINT_MAX = PyNumber_Subtract(tobj, ft_gv_1);
    Py_DECREF(tobj);
    
    tobj = PyNumber_Power(ft_gv_2, ft_gv_int_num_bits_minus_1, Py_None);
    ft_gv_INT_MIN = PyNumber_Negative(tobj);
    Py_DECREF(tobj);
    
    tobj = PyNumber_Power(ft_gv_2, ft_gv_int_num_bits_minus_1, Py_None);
    ft_gv_INT_MAX = PyNumber_Subtract(tobj, ft_gv_1);
    Py_DECREF(tobj);
    
    ft_gv_numpy = PyImport_ImportModule("numpy");
    if (PyErr_Occurred() != NULL) goto exception;
    
    ft_gv_numpy_ndarray = (PyTypeObject *)PyObject_GetAttrString(ft_gv_numpy, "ndarray");
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
    
    ft_gv_labrad_units_ValueArray = (PyTypeObject *)PyObject_GetAttrString(ft_gv_labrad_units, "ValueArray");
    if (PyErr_Occurred() != NULL) goto exception;
    
    ft_gv_initialized = TRUE;

    return SUCCESS;
    
exception:

    return EXCEPTION_RAISED;
}
 
int ft_system_supported() {
    if (sizeof(char) != LABRAD_BOOL_SIZE ||
        sizeof(int) != LABRAD_INT_SIZE ||
        sizeof(long long int) != LABRAD_LONG_SIZE ||
        sizeof(double) != LABRAD_FLOAT_SIZE)
        return FALSE;
    
    return TRUE;
}

void ft_detect_system_endianness() {
    int i;
    char buf[LABRAD_INT_SIZE];
    
    i = 1;
    memcpy(buf, &i, LABRAD_INT_SIZE);
    
    if (buf[0] == 0) ft_gv_system_big_endian = TRUE;
    else ft_gv_system_big_endian = FALSE;
}

int ft_set_send_endianness(PyObject *endianness) {
    PyObject *big_endian, *little_endian;
    
    big_endian = PyString_FromString(BIG_ENDIAN);
    little_endian = PyString_FromString(LITTLE_ENDIAN);
    
    if (!PyString_Check(endianness)) {
        PyErr_SetString(PyExc_TypeError, "endianness must be '>' or '<'");
        goto exception;
    }
    
    if (PyObject_RichCompareBool(endianness, big_endian, Py_EQ) == TRUE) {
        ft_gv_send_big_endian = TRUE;
    }
    else if (PyObject_RichCompareBool(endianness, little_endian, Py_EQ) == TRUE) {
        ft_gv_send_big_endian = FALSE;
    }
    else {
        PyErr_SetString(PyExc_SyntaxError, "endianness must be '>' or '<'");
        goto exception;
    }
    
    Py_DECREF(big_endian);
    Py_DECREF(little_endian);
    
    return TRUE;
    
exception:
    
    Py_DECREF(big_endian);
    Py_DECREF(little_endian);
    
    return FALSE;
}

COBJ *ft_allocate_memory_for_cobj() {
    return (COBJ *)malloc(sizeof(COBJ));
}

void ft_print_cobj(COBJ *cobj) {
    unsigned int ui, N;
    
    if (cobj == NULL) return;
    
    printf("\n%p\n", cobj);
    switch (cobj->type) {
        case EMPTY:
            printf("type: EMPTY\n");
            break;
        case BOOL:
            printf("type: BOOL\n");
            break;
        case UINT31:
            printf("type: UINT31\n");
            break;
        case INT32:
            printf("type: INT32\n");
            break;
        case UINT32:
            printf("type: UINT32\n");
            break;
        case FLOAT64:
            printf("type: FLOAT64\n");
            break;
        case COMPLEX128:
            printf("type: COMPLEX128\n");
            break;
        case FLOAT64_SU:
            printf("type: FLOAT64_SU\n");
            break;
        case COMPLEX128_SU:
            printf("type: COMPLEX128_SU\n");
            break;
        case STRING:
            printf("type: STRING\n");
            break;
        case CLUSTER:
            printf("type: CLUSTER\n");
            break;
        case LIST:
            printf("type: LIST\n");
            break;
        case NDARRAY:
            printf("type: NDARRAY\n");
            break;
        case NDARRAY_SU:
            printf("type: NDARRAY_SU\n");
            break;
        case TIME:
            printf("type: TIME\n");
            break;
        case ERROR:
            printf("type: ERROR\n");
            break;
    }
    switch (cobj->type) {
        case NDARRAY:
        case NDARRAY_SU:
        case ERROR:
            printf("subtype: %d\n", cobj->subtype);
    }
    switch (cobj->type) {
        case BOOL:
            if (cobj->i == FALSE) printf("i: FALSE\n");
            else printf("i: TRUE\n");
            break;
        case UINT31:
        case INT32:
            printf("i: %d\n", cobj->i);
            break;
    }
    switch (cobj->type) {
        case UINT32:
        case FLOAT64_SU:
        case COMPLEX128_SU:
        case CLUSTER:
        case LIST:
        case STRING:
        case NDARRAY:
        case NDARRAY_SU:
            printf("n: %u\n", cobj->n);
    }
    switch (cobj->type) {
        case FLOAT64:
        case FLOAT64_SU:
        case COMPLEX128:
        case COMPLEX128_SU:
            printf("x: %g\n", cobj->x);
    }
    switch (cobj->type) {
        case COMPLEX128:
        case COMPLEX128_SU:
            printf("y: %g\n", cobj->y);
    }
    switch (cobj->type) {
        case FLOAT64_SU:
        case COMPLEX128_SU:
        case STRING:
        case NDARRAY_SU:
        case ERROR:
            printf("str: %s\n", cobj->str);
    }
    switch (cobj->type) {
        case CLUSTER:
        case LIST:
            for (ui=0; ui<cobj->n; ui++) {
                printf("cobj_arr[%u]: %p\n", ui, cobj->cobj_arr[ui]);
            }
            for (ui=0; ui<cobj->n; ui++) {
                ft_print_cobj(cobj->cobj_arr[ui]);
            }
    }
    switch (cobj->type) {
        case NDARRAY:
        case NDARRAY_SU:
            N = 1;
            for (ui=0; ui<cobj->n; ui++) {
                printf("dim_arr[%u]: %u\n", ui, cobj->dim_arr[ui]);
                N *= cobj->dim_arr[ui];
            }
            for (ui=0; ui<N; ui++) {
                if (cobj->subtype == BOOL) {
                    printf("arr[%u]: %d\n", ((char *)cobj->arr)[ui]);
                }
                else if (cobj->subtype == UINT31 || cobj->subtype == INT32) {
                    printf("arr[%u]: %d\n", ((int *)cobj->arr)[ui]);
                }
                else if (cobj->subtype == UINT32) {
                    printf("arr[%u]: %u\n", ((unsigned int *)cobj->arr)[ui]);
                }
                else if (cobj->subtype == FLOAT64 || cobj->subtype == COMPLEX128) {
                    printf("arr[%u]: %g\n", ((double *)cobj->arr)[ui]);
                }
            }
    }
    switch (cobj->type) {
        case TIME:
            printf("secs: %ld\n", cobj->secs);
            printf("usecs: %ld\n", cobj->usecs);
    }
}

void ft_free_cobj(COBJ *cobj) {
    unsigned int ui;
    
    if (cobj == NULL) return;
    
    switch (cobj->type) {
        case FLOAT64_SU:
        case COMPLEX128_SU:
        case STRING:
        case NDARRAY_SU:
            free(cobj->str);
    }
    
    switch (cobj->type) {
        case CLUSTER:
        case LIST:
            for (ui=0; ui<cobj->n; ui++) {
                ft_free_cobj(cobj->cobj_arr[ui]);
            }
            free(cobj->cobj_arr);
    }
    
    switch (cobj->type) {
        case NDARRAY:
        case NDARRAY_SU:
            free(cobj->dim_arr);
            free(cobj->arr);
    }
    
    free(cobj);
}

char *ft_get_unit_string(PyObject *obj) {
    int n;
    char *str1, *str2;
    PyObject *tobj1, *tobj2;
    
    tobj1 = PyObject_GetAttrString(obj, "unit");
    tobj2 = PyObject_GetAttrString(tobj1, "name");
    str1 = ((PyStringObject *)tobj2)->ob_sval;
    n = PyString_GET_SIZE(tobj2);
    str2 = (char *)malloc((n+1)*sizeof(char));
    strcpy(str2, str1);
    Py_DECREF(tobj2);
    Py_DECREF(tobj1);
    
    return str2;
}

COBJ *ft_convert_to_standard_units(COBJ *cobj) {
    if (cobj->type == FLOAT64) cobj->type = FLOAT64_SU;
    else if (cobj->type == COMPLEX128) cobj->type = COMPLEX128_SU;
    else if (cobj->type == NDARRAY) cobj->type = NDARRAY_SU;
    else {
        PyErr_SetString(PyExc_TypeError, "unable to conver WithUnit to standard units (SU)");
        ft_free_cobj(cobj);
        return NULL;
    }
    
    return cobj;
}

PyObject *ft_test(PyObject *self, PyObject *args) {
    int i, n;
    PyObject *tc_mod, *tc_list, *tc_i;
    COBJ *cobj;

    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }
    
    tc_mod = PyImport_ImportModule("fasttypes_testcases");
    if (PyErr_Occurred() != NULL) goto exception;
    
    tc_list = PyObject_GetAttrString(tc_mod, "passcases");
    if (tc_list == NULL || !PyList_Check(tc_list)) goto exception;
    
    n = PyList_GET_SIZE(tc_list);
    for (i=0; i<n; i++) {
        printf("%d\n", i);
        tc_i = PyList_GET_ITEM(tc_list, i);

        if (tc_i != NULL) {
            PyObject_Print(tc_i, stdout, Py_PRINT_RAW);
            printf("\n");
            cobj = ft_create_cobj_from_pyobj(tc_i);
            if (cobj == NULL) goto exception;
            ft_print_cobj(cobj);
            printf("\n");
            ft_free_cobj(cobj);
        }
    }
    
    printf("All %d test cases passed.\n", n);
    
    Py_DECREF(tc_list);
    Py_DECREF(tc_mod);
    
    Py_INCREF(Py_None);
    return Py_None;
    
exception:

    if (tc_list != NULL) Py_DECREF(tc_list);
    if (tc_mod != NULL) Py_DECREF(tc_mod);

    return NULL;
}

static PyMethodDef fasttypes_methods[] = {
    {"flatten", (PyCFunction)ft_flatten, METH_VARARGS | METH_KEYWORDS, "flatten() doc string."},
    {"test", ft_test, METH_VARARGS, "test() doc string."},
    {NULL, NULL}
};

PyMODINIT_FUNC initfasttypes(void) {
    Py_InitModule("fasttypes", fasttypes_methods);
}