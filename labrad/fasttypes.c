#include "Python.h"

// NOTES:
// - It seems Python.h modifies assert() so it does not trigger program termination on failure. exit() terminates the interpreter.

// Get more agreement with existing flatten/unflatten

/*
Currently supported: int, long, float, complex, string, bool, 1D lists, tuples, all dimensionless

Adding a type:
1- ft_size, #define for type size if needed
2- ft_create_unambiguous_type_string
3- ft_create_type_string
4- ft_find_beginning_next_type_token
5- ft_type_strings_equivalent
6- ft_write_to_buf
7- ft_flatten_no_parse
8- ft_unflatten_no_parse
9- add test cases

Future work, support:
import numpy as np
import labrad.units as U
fasttypes.flatten(4*U.ns) -> typetag: v[ns]
fasttypes.flatten((2+7j)*U.Unit('Volt')) -> typetag: c[ns]
fasttypes.flatten(np.eye(4)*U.GHz) -> typetag: *2v[GHz]
fasttypes.flatten(4*GHz*2*ns) -> typetag: v[]
*/

#define BIG 1
#define LITTLE 0


// FRESH START -----------------------------------------------------

#define TRUE 1
#define FALSE 0
#define BIG_ENDIAN ">"
#define LITTLE_ENDIAN "<"
#define EXCEPTION_RAISED -1
#define FIXED_BOOL_SIZE 1
#define FIXED_INT_SIZE 4
#define FIXED_LONG_SIZE 4
#define FIXED_FLOAT_SIZE 8
#define FIXED_COMPLEX_SIZE 16
#define PyStringObject_SIZE (offsetof(PyStringObject, ob_sval) + 1)

// b, i, w, v[], c[], s, *, *n, (), ?, _
#define BOOL 0
#define CHAR 1
#define UINT31 2
#define INT32 3
#define UINT32 4
#define FLOAT64 5
#define COMPLEX128 6
#define STRING 7
#define LIST 8
#define TUPLE 9
#define NDARRAY 10
#define ARBITRARY 11
#define DIMENSION 12
#define EMPTY 13

typedef struct type_tree TYPE_TREE;
typedef struct transform_tree TRANSFORM_TREE;

struct type_tree {
    int type;
    int modifiable;
    int count;
    TYPE_TREE *next;
    TYPE_TREE *sub;
    char *dimension;
};

struct transform_tree {
    TYPE_TREE *ttr;
    int n;
    unsigned int mark;
    TRANSFORM_TREE **branch;
};

// global variables (gv)
int ft_gv_initialized = FALSE;
int ft_gv_system_big_endian = FALSE;
int ft_gv_send_big_endian = TRUE;
PyObject *ft_gv_0 = NULL;
PyObject *ft_gv_1 = NULL;
PyObject *ft_gv_2 = NULL;
PyObject *ft_gv_long_num_bits = NULL;
PyObject *ft_gv_long_num_bits_minus_1 = NULL;
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
TRANSFORM_TREE *ft_gv_transform_tree = NULL;
unsigned int ft_gv_mark = 0;

PyObject *ft_flatten(PyObject *self, PyObject *args, PyObject *keywds);
int ft_initialize();
int ft_system_supported();
void ft_detect_system_endianness();
int ft_set_send_endianness(PyObject *endianness);
PyObject *ft_flatten_with_type_tag(PyObject *obj, PyObject *tt);
TYPE_TREE *ft_create_type_tree(PyObject *tt);
TYPE_TREE *ft_create_type_tree_char(char *buf, int *iptr, int n);
TYPE_TREE *ft_create_type_tree_node(int type, int modifiable);
TYPE_TREE *ft_create_type_tree_dimension(char *buf, int *iptr, int n, int modifiable);
TYPE_TREE *ft_create_type_tree_ndarray(char *buf, int *iptr, int n, int modifiable);
void ft_free_type_tree(TYPE_TREE *ttr);
void ft_print_type_tree(TYPE_TREE *ttr);
void ft_print_type_tree_recurse(TYPE_TREE *ttr, int level);
TYPE_TREE *ft_tailor_type_tree_to_obj(PyObject *obj, TYPE_TREE *ttr);
void ft_init_global_transform_tree();
TRANSFORM_TREE *ft_create_transform_tree_node();
void ft_insert_type_in_transform_tree_node(TRANSFORM_TREE *node, int type, int dim_flag);
void ft_insert_transform_tree_node_in_another(TRANSFORM_TREE *dest, TRANSFORM_TREE *src);
void ft_free_transform_tree(TRANSFORM_TREE *trtr);
TRANSFORM_TREE *ft_find_transform_tree_node(int type, int dim_flag);
TRANSFORM_TREE *ft_find_transform_tree_node_recurse(TRANSFORM_TREE *trtr, int type, int dim_flag);
void ft_print_global_transform_tree();
void ft_print_transform_tree_recurse(TRANSFORM_TREE *trtr, int level);
void ft_zero_transform_tree();
void ft_zero_transform_tree_recurse(TRANSFORM_TREE *trtr);
void ft_mark_parents(TRANSFORM_TREE *trtr);
void ft_mark_parents_recurse(TRANSFORM_TREE *trtr);
TRANSFORM_TREE *ft_find_marked_node(TRANSFORM_TREE *trtr);
TRANSFORM_TREE *ft_find_common_parent_type(int type1, int dim_flag1, int type2, int dim_flag2);
void ft_type_tree_to_ints(TYPE_TREE *ttr, int *type_ptr, int *dim_flag_ptr);
int ft_obj_to_ints(PyObject *obj, int *type_ptr, int *dim_flag_ptr);
char *ft_get_unit_string(PyObject *obj);

PyObject *ft_flatten(PyObject *self, PyObject *args, PyObject *keywds) {
    int i, n;
    PyObject *obj, *types, *endianness, *sobj, *lobj, *robj;
    char *kwlist[] = {"obj", "types", "endianness", NULL};
    
    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }
    
    obj = types = endianness = sobj = lobj = NULL;
    
    if (!PyArg_ParseTupleAndKeywords(args, keywds, "O|OO", kwlist, &obj, &types, &endianness)) goto exception;
    
    if (endianness != NULL) {
        if (!ft_set_send_endianness(endianness)) goto exception;
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
    
    /*
    printf("xfm begin:\n");
    ft_print_global_transform_tree();
    printf("xfm end:\n");
    */
    
    n = PyList_GET_SIZE(types);
    for (i=0; i<n; i++) {
        // printf("i: %d, tt: ", i);
        robj = ft_flatten_with_type_tag(obj, PyList_GET_ITEM(types, i));
        if (robj != NULL) break;
        if (PyErr_Occurred() != NULL) PyErr_Print();
    }
    if (robj == NULL) {
        PyErr_SetString(PyExc_Exception, "unable to flatten obj");
        goto exception;
    }

    if (lobj != NULL) Py_DECREF(lobj);
    
    Py_INCREF(Py_None);
    return Py_None;

exception:
    
    if (lobj != NULL) Py_DECREF(lobj);
    
    return NULL;
}

int ft_initialize() {
    PyObject *t;
    
    if (!ft_system_supported()) {
        PyErr_SetString(PyExc_AssertionError, "system has unsupported data type sizes");
        return EXCEPTION_RAISED;
    }

    ft_detect_system_endianness();
    
    ft_gv_0 = PyInt_FromLong(0);
    ft_gv_1 = PyInt_FromLong(1);
    ft_gv_2 = PyInt_FromLong(2);
    ft_gv_long_num_bits = PyInt_FromLong(8*FIXED_LONG_SIZE);
    ft_gv_long_num_bits_minus_1 = PyInt_FromLong(8*FIXED_LONG_SIZE-1);
    
    t = PyNumber_Power(ft_gv_2, ft_gv_long_num_bits, Py_None);
    ft_gv_UINT_MAX = PyNumber_Subtract(t, ft_gv_1);
    Py_DECREF(t);
    // PyObject_Print(ft_gv_UINT_MAX, stdout, Py_PRINT_RAW);
    
    t = PyNumber_Power(ft_gv_2, ft_gv_long_num_bits_minus_1, Py_None);
    ft_gv_INT_MIN = PyNumber_Negative(t);
    Py_DECREF(t);
    
    t = PyNumber_Power(ft_gv_2, ft_gv_long_num_bits_minus_1, Py_None);
    ft_gv_INT_MAX = PyNumber_Subtract(t, ft_gv_1);
    Py_DECREF(t);
    
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
    
    ft_init_global_transform_tree();
    
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
    
    if (buf[0] == 0) ft_gv_system_big_endian = TRUE;
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

PyObject *ft_flatten_with_type_tag(PyObject *obj, PyObject *tt) {
    TYPE_TREE *ttr;
    
    // PyObject_Print(tt, stdout, Py_PRINT_RAW);
    // printf("\n");
    
    ttr = ft_create_type_tree(tt);
    if (ttr == NULL) goto exception;
    ft_print_type_tree(ttr);
    
    // ***
    if (ft_tailor_type_tree_to_obj(obj, ttr) == NULL) goto exception;
    ft_print_type_tree(ttr);
    
    ft_free_type_tree(ttr);
    
    return NULL;
    
exception:
    
    return NULL;
}

TYPE_TREE *ft_create_type_tree(PyObject *tt) {
    int i, n;
    char *buf;
    TYPE_TREE *ttr;
    
    ttr = NULL;
    
    if (!PyString_Check(tt)) {
        PyErr_SetString(PyExc_TypeError, "type tag must be a string");
        goto exception;
    }
    
    i = 0;
    n = PyString_GET_SIZE(tt);
    buf = ((PyStringObject *)tt)->ob_sval;
    // printf("buf: %s\n", buf);
    
    if (n == 0) {
        PyErr_SetString(PyExc_SyntaxError, "type tag must have non-zero length");
        goto exception;
    }
    
    ttr = ft_create_type_tree_char(buf, &i, n);
    if (ttr == NULL) goto exception;
    // printf("after ft_create_type_tree_char i: %d, n: %d\n", i, n);
    
    if (i != n) {
        PyErr_SetString(PyExc_SyntaxError, "superfluous characters at end of type tag");
        ft_free_type_tree(ttr);
        goto exception;
    }
    
    return ttr;
    
exception:
    
    return NULL;
}

TYPE_TREE *ft_create_type_tree_char(char *buf, int *iptr, int n) {
    int i;
    TYPE_TREE *ttr, *sub;
    
    i = *iptr;
    ttr = NULL;
    
    if (i == n) return NULL;
    
    if (buf[i] == 'b') {
        (*iptr)++;
        return ft_create_type_tree_node(BOOL, FALSE);
    }
    else if (buf[i] == 'i') {
        (*iptr)++;
        return ft_create_type_tree_node(INT32, FALSE);
    }
    else if (buf[i] == 'w') {
        (*iptr)++;
        return ft_create_type_tree_node(UINT32, FALSE);
    }
    else if (buf[i] == 'v' || buf[i] == 'c') {
        if (buf[i] == 'v') ttr = ft_create_type_tree_node(FLOAT64, FALSE);
        if (buf[i] == 'c') ttr = ft_create_type_tree_node(COMPLEX128, FALSE);
        if (ttr == NULL) goto exception;
        i++;
        if (i < n-1 && buf[i] == '[') {
            i++;
            ttr->sub = ft_create_type_tree_dimension(buf, &i, n, FALSE);
            if (ttr->sub == NULL) {
                ft_free_type_tree(ttr);
                goto exception;
            }
            *iptr = i;
            return ttr;
        }
        else {
            *iptr = i;
            return ttr;
        }
    }
    else if (buf[i] == 's') {
        ttr = ft_create_type_tree_node(STRING, FALSE);
        if (ttr == NULL) goto exception;
        ttr->sub = ft_create_type_tree_node(CHAR, FALSE);
        if (ttr->sub == NULL) {
            ft_free_type_tree(ttr);
            goto exception;
        }
        (*iptr)++;
        return ttr;
    }
    else if (buf[i] == '*') {
        i++;
        if (i == n) {
            PyErr_SetString(PyExc_SyntaxError, "list with no sub type tag");
            goto exception;
        }
        if (isdigit(buf[i])) {
            // printf("here\n");
            ttr = ft_create_type_tree_ndarray(buf, &i, n, FALSE);
        }
        else {
            ttr = ft_create_type_tree_node(LIST, FALSE);
        }
        if (ttr == NULL) goto exception;
        ttr->sub = ft_create_type_tree_char(buf, &i, n);
        if (ttr->sub == NULL) {
            ft_free_type_tree(ttr);
            goto exception;
        }
        *iptr = i;
        return ttr;
    }
    else if (buf[i] == '(') {
        i++;
        if (i == n) {
            PyErr_SetString(PyExc_SyntaxError, "tuple with no )");
            goto exception;
        }
        ttr = ft_create_type_tree_node(TUPLE, FALSE);
        if (ttr == NULL) goto exception;

        while (i < n && buf[i] != ')') {
            if (ttr->sub == NULL) {
                sub = ft_create_type_tree_char(buf, &i, n);
                if (sub == NULL) {
                    ft_free_type_tree(ttr);
                    goto exception;
                }
                ttr->sub = sub;
            }
            else {
                sub->next = ft_create_type_tree_char(buf, &i, n);
                if (sub->next == NULL) {
                    ft_free_type_tree(ttr);
                    goto exception;
                }
                sub = sub->next;
            }
        }
        if (i == n) {
            PyErr_SetString(PyExc_SyntaxError, "tuple with no )");
            goto exception;
        }
        *iptr = i+1;
        return ttr;
    }
    else if (buf[i] == '?') {
        (*iptr)++;
        return ft_create_type_tree_node(ARBITRARY, TRUE);
    }
    else if (buf[i] == '_') {
        (*iptr)++;
        return ft_create_type_tree_node(EMPTY, FALSE);
    }
    else {
        PyErr_SetString(PyExc_SyntaxError, "invalid type tag");
        goto exception;
    }
    
exception:
    
    return NULL;
}

TYPE_TREE *ft_create_type_tree_node(int type, int modifiable) {
    TYPE_TREE *ttr;
    
    ttr = (TYPE_TREE *)malloc(sizeof(TYPE_TREE));
    
    ttr->type = type;
    ttr->modifiable = modifiable;
    ttr->count = 0;
    ttr->next = NULL;
    ttr->sub = NULL;
    ttr->dimension = NULL;
    
    return ttr;
}

TYPE_TREE *ft_create_type_tree_dimension(char *buf, int *iptr, int n, int modifiable) {
    int i;
    TYPE_TREE *ttr;
    char *s;
    
    ttr = ft_create_type_tree_node(DIMENSION, modifiable);
    
    i = 0;
    while (i < n) {
        if (buf[*iptr + i] == ']') break;
        i++;
    }
    if (i == n) {
        PyErr_SetString(PyExc_SyntaxError, "missing closing ]");
        ft_free_type_tree(ttr);
        goto exception;
    }
    ttr->count = i;
    
    s = (char *)malloc((i+1)*sizeof(char));

    strncpy(s, buf + *iptr, i);
    s[i] = '\0';
    ttr->dimension = s;
    
    *iptr += i+1;
    return ttr;
    
exception:
    
    return NULL;
}

TYPE_TREE *ft_create_type_tree_ndarray(char *buf, int *iptr, int n, int modifiable) {
    int i;
    TYPE_TREE *ttr;
    char *s;
    
    ttr = ft_create_type_tree_node(NDARRAY, modifiable);
    
    i = 0;
    while (i < n) {
        if (!isdigit(buf[*iptr + i])) break;
        i++;
    }
    if (i == n) {
        PyErr_SetString(PyExc_SyntaxError, "ndarray has no sub type");
        ft_free_type_tree(ttr);
        goto exception;
    }
    ttr->count = i;
    
    s = (char *)malloc((i+1)*sizeof(char));
    
    strncpy(s, buf + *iptr, i);
    s[i] = '\0';
    // printf("s: %s\n", s);
    ttr->dimension = s;
    
    *iptr += i;
    return ttr;
    
exception:
    
    return NULL;
}

void ft_free_type_tree(TYPE_TREE *ttr) {
    if (ttr == NULL) return;
    
    ft_free_type_tree(ttr->next);
    ft_free_type_tree(ttr->sub);
    free(ttr->dimension);
    free(ttr);
}

void ft_print_type_tree(TYPE_TREE *ttr) {
    ft_print_type_tree_recurse(ttr, 0);
}

void ft_print_type_tree_recurse(TYPE_TREE *ttr, int level) {
    if (ttr == NULL) return;
    
    printf("level: %d\n", level);
    printf("ptr: %p\n", ttr);
    printf("type: %d\n", ttr->type);
    printf("count: %d\n", ttr->count);
    printf("next: %p\n", ttr->next);
    printf("sub: %p\n", ttr->sub);
    printf("dimension: %s\n\n", ttr->dimension);
    
    ft_print_type_tree_recurse(ttr->sub, level+1);
    ft_print_type_tree_recurse(ttr->next, level);
}

// ***
TYPE_TREE *ft_tailor_type_tree_to_obj(PyObject *obj, TYPE_TREE *ttr) {
    int type1, dim_flag1, type2, dim_flag2, type3, dim_flag3;
    char *str;
    TRANSFORM_TREE *trtr;
    
    int i, n;
    TYPE_TREE *sub;
    PyObject *obj_i;
    
    if (ft_obj_to_ints(obj, &type1, &dim_flag1) == EXCEPTION_RAISED) goto exception;
    ft_type_tree_to_ints(ttr, &type2, &dim_flag2);
    
    trtr = ft_find_common_parent_type(type1, dim_flag1, type2, dim_flag2);
    ft_type_tree_to_ints(trtr->ttr, &type3, &dim_flag3);
    
    if (type3 != type2) {
        if (ttr->modifiable == FALSE) {
            PyErr_SetString(PyExc_SyntaxError, "type tag and object do not match");
            goto exception;
        }
        ttr->type = type3;
    }
    
    if (dim_flag3 != dim_flag2) {
        if (dim_flag2 == FALSE) {
            PyErr_SetString(PyExc_SyntaxError, "type tag and object do not match");
            goto exception;
        }
        ft_free_type_tree(ttr->sub);
        ttr->sub = NULL;
    }
    else if (dim_flag2 == TRUE) {
        str = ft_get_unit_string(obj);
        if (ttr->sub->modifiable == TRUE) {
            ttr->sub->dimensions = str;
            ttr->sub->modifiable = FALSE;
        }
        // *** ensure dims match
        else {
            if (strcmp(str, ttr->sub->dimensions) != 0) 
                PyErr_SetString(PyExc_SyntaxError, "only identical units supported");
                goto exception;
            }
        }
    }
    
    ttr->count++;
    
    // *** string, list, ndarray, tuple handling from ? type tag
    if (PyString_Check(obj)) {
        if (ttr->type != STRING) goto exception;
        sub = ttr->sub;
        if (sub == NULL || sub->type != CHAR) goto exception;
        sub->count += PyString_GET_SIZE(obj);
    }
    else if (PyList_Check(obj)) {
        if (ttr->type != LIST) goto exception;
        ttr->count++;
        n = PyList_GET_SIZE(obj);
        if (ttr->sub == NULL) goto exception;
        for (i=0; i<n; i++) {
            obj_i = PyList_GET_ITEM(obj, i);
            ttr->sub = ft_tailor_type_tree_to_obj(obj_i, ttr->sub);
            if (ttr->sub == NULL) goto exception;
        }
        return ttr;
    }
    
exception:
    
    // PyErr_SetString(PyExc_SyntaxError, "type tag and object do not match");
    ft_free_type_tree(ttr);
    
    return NULL;
}

void ft_init_global_transform_tree() {
    TRANSFORM_TREE *trtr_node1, *trtr_node2;
    
    // ARBITRARY
    ft_gv_transform_tree = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(ft_gv_transform_tree, ARBITRARY, TRUE);
    
    // EMPTY
    trtr_node1 = ft_find_transform_tree_node(ARBITRARY, TRUE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, EMPTY, TRUE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // BOOL
    trtr_node1 = ft_find_transform_tree_node(EMPTY, TRUE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, BOOL, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // STRING
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, STRING, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // UINT31
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, UINT31, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // INT32
    trtr_node1 = ft_find_transform_tree_node(UINT31, FALSE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, INT32, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // UINT32
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, UINT32, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // FLOAT64 FALSE
    trtr_node1 = ft_find_transform_tree_node(INT32, FALSE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, FLOAT64, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    trtr_node1 = ft_find_transform_tree_node(UINT32, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // COMPLEX128 FALSE
    trtr_node1 = ft_find_transform_tree_node(FLOAT64, FALSE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, COMPLEX128, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // FLOAT64 TRUE
    trtr_node1 = ft_find_transform_tree_node(EMPTY, TRUE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, FLOAT64, TRUE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // COMPLEX128 TRUE
    trtr_node1 = ft_find_transform_tree_node(FLOAT64, TRUE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, COMPLEX128, TRUE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // NDARRAY FALSE
    trtr_node1 = ft_find_transform_tree_node(EMPTY, TRUE);
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, NDARRAY, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // NDARRAY TRUE
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, NDARRAY, TRUE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // LIST FALSE
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, LIST, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
    
    // TUPLE FALSE
    trtr_node2 = ft_create_transform_tree_node();
    ft_insert_type_in_transform_tree_node(trtr_node2, TUPLE, FALSE);
    ft_insert_transform_tree_node_in_another(trtr_node1, trtr_node2);
}

TRANSFORM_TREE *ft_create_transform_tree_node() {
    TRANSFORM_TREE *trtr;
    
    trtr = (TRANSFORM_TREE *)malloc(sizeof(TRANSFORM_TREE));
    
    trtr->ttr = NULL;
    trtr->n = 0;
    trtr->mark = 0;
    trtr->branch = NULL;
    
    return trtr;
}

void ft_insert_type_in_transform_tree_node(TRANSFORM_TREE *node, int type, int dim_flag) {
    TYPE_TREE *ttr, *dim;
    
    ttr = ft_create_type_tree_node(type, FALSE);
    
    if (dim_flag) {
        dim = ft_create_type_tree_node(DIMENSION, FALSE);
        ttr->sub = dim;
    }
    
    node->ttr = ttr;
}

void ft_insert_transform_tree_node_in_another(TRANSFORM_TREE *dest, TRANSFORM_TREE *src) {
    dest->n++;
    dest->branch = (TRANSFORM_TREE **)realloc(dest->branch, dest->n*sizeof(TRANSFORM_TREE *));
    dest->branch[dest->n - 1] = src;
}

void ft_free_transform_tree(TRANSFORM_TREE *trtr) {
    int i;
    
    ft_free_type_tree(trtr->ttr);
    
    for (i=0; i<trtr->n; i++) {
        ft_free_transform_tree(trtr->branch[i]);
    }
    
    free(trtr->branch);
    free(trtr);
}

TRANSFORM_TREE *ft_find_transform_tree_node(int type, int dim_flag) {
    return ft_find_transform_tree_node_recurse(ft_gv_transform_tree, type, dim_flag);
}

TRANSFORM_TREE *ft_find_transform_tree_node_recurse(TRANSFORM_TREE *trtr, int type, int dim_flag) {
    int local_dim_flag, i, n;
    TRANSFORM_TREE *trtr_node;
    TYPE_TREE *ttr;
    
    if (trtr == NULL) return NULL;
    
    ft_gv_mark++;
    if (ft_gv_mark == 0) {
        ft_zero_transform_tree();
        ft_gv_mark++;
    }
    
    if (trtr->mark == ft_gv_mark) return NULL;
    
    ttr = trtr->ttr;
    local_dim_flag = (ttr->sub != NULL) ? TRUE : FALSE;
    
    if (dim_flag && !local_dim_flag) return NULL;
    if (ttr->type == type && local_dim_flag == dim_flag) return trtr;
    trtr->mark = ft_gv_mark;
    
    n = trtr->n;
    for (i=0; i<n; i++) {
        trtr_node = ft_find_transform_tree_node_recurse(trtr->branch[i], type, dim_flag);
        if (trtr_node != NULL) return trtr_node;
    }
    
    return NULL;
}

void ft_print_global_transform_tree() {
    ft_print_transform_tree_recurse(ft_gv_transform_tree, 0);
}

void ft_print_transform_tree_recurse(TRANSFORM_TREE *trtr, int level) {
    int i;
    
    if (trtr == NULL) return;
    
    printf("xfm level: %d\n", level);
    ft_print_type_tree(trtr->ttr);
    
    for (i=0; i<trtr->n; i++) {
        ft_print_transform_tree_recurse(trtr->branch[i], level+1);
    }
}

void ft_zero_transform_tree() {
    ft_zero_transform_tree_recurse(ft_gv_transform_tree);
}

void ft_zero_transform_tree_recurse(TRANSFORM_TREE *trtr) {
    int i;
    
    if (trtr == NULL) return;
    if (trtr->mark == 0) return;
    
    trtr->mark = 0;
    
    for (i=0; i<trtr->n; i++) {
        ft_zero_transform_tree_recurse(trtr->branch[i]);
    }
}

void ft_mark_parents(TRANSFORM_TREE *trtr) {
    ft_gv_mark++;
    if (ft_gv_mark == 0) {
        ft_zero_transform_tree();
        ft_gv_mark++;
    }
    
    ft_mark_parents_recurse(trtr);
}

void ft_mark_parents_recurse(TRANSFORM_TREE *trtr) {
    int i;
    
    if (trtr == NULL) return;
    if (trtr->mark == ft_gv_mark) return;
    
    trtr->mark = ft_gv_mark;
    
    for (i=0; i<trtr->n; i++) {
        ft_mark_parents_recurse(trtr->branch[i]);
    }
}

TRANSFORM_TREE *ft_find_marked_node(TRANSFORM_TREE *trtr) {
    int i;
    TRANSFORM_TREE *trtr_ret;
    
    if (trtr == NULL) return NULL;
    if (trtr->mark == ft_gv_mark) return trtr;
    
    for (i=0; i<trtr->n; i++) {
        trtr_ret = ft_find_marked_node(trtr->branch[i]);
        if (trtr_ret != NULL) return trtr_ret;
    }
    
    return NULL;
}

TRANSFORM_TREE *ft_find_common_parent_type(int type1, int dim_flag1, int type2, int dim_flag2) {
    TRANSFORM_TREE *trtr1, *trtr2;
    
    trtr1 = ft_find_transform_tree_node(type1, dim_flag1);
    trtr2 = ft_find_transform_tree_node(type2, dim_flag2);
    
    ft_mark_parents(trtr1);
    
    return ft_find_marked_node(trtr2);
}

void ft_type_tree_to_ints(TYPE_TREE *ttr, int *type_ptr, int *dim_flag_ptr) {
    *type_ptr = ttr->type;
    *dim_flag_ptr = (ttr->sub != NULL) ? TRUE : FALSE;
}

int ft_obj_to_ints(PyObject *obj, int *type_ptr, int *dim_flag_ptr) {
    if (obj == Py_None) {
        *type_ptr = EMPTY;
        *dim_flag_ptr = TRUE;
    }
    else if (PyBool_Check(obj)) {
        *type_ptr = BOOL;
        *dim_flag_ptr = FALSE;
    }
    else if (PyString_Check(obj)) {
        *type_ptr = STRING;
        *dim_flag_ptr = FALSE;
    }
    else if (PyInt_Check(obj) || PyLong_Check(obj)) {
        if (PyObject_Compare(obj, ft_gv_0) < 0) {
            if (PyObject_Compare(obj, ft_gv_INT_MIN) < 0) goto exception;
            *type_ptr = INT32;
            *dim_flag_ptr = FALSE;
        }
        else if (PyObject_Compare(obj, ft_gv_UINT_MAX) > 0) goto exception;
        else if (PyObject_Compare(obj, ft_gv_INT_MAX) > 0) {
            *type_ptr = UINT32;
            *dim_flag_ptr = FALSE;
        }
        else {
            *type_ptr = INT32;
            *dim_flag_ptr = FALSE;
        }
    }
    else if (PyObject_TypeCheck(obj, ft_gv_labrad_units_WithUnit)) {
        if (PyObject_TypeCheck(obj, ft_gv_labrad_units_Value)) {
            *type_ptr = FLOAT64;
            *dim_flag_ptr = TRUE;
        }
        else if (PyObject_TypeCheck(obj, ft_gv_labrad_units_Complex)) {
            *type_ptr = COMPLEX128;
            *dim_flag_ptr = TRUE;
        }
        else if (PyObject_TypeCheck(obj, ft_gv_labrad_units_ValueArray)) {
            *type_ptr = NDARRAY;
            *dim_flag_ptr = TRUE;
        }
    }
    else if (PyObject_TypeCheck(obj, ft_gv_numpy_ndarray)) {
        *type_ptr = NDARRAY;
        *dim_flag_ptr = FALSE;
    }
    else if (PyList_Check(obj)) {
        *type_ptr = LIST;
        *dim_flag_ptr = FALSE;
    }
    else if (PyTuple_Check(obj)) {
        *type_ptr = LIST;
        *dim_flag_ptr = FALSE;
    }
    else goto exception;
    
    return TRUE;
    
exception:
    
    PyErr_SetString(PyExc_TypeError, "unsupported python object");
    
    return EXCEPTION_RAISED;
}

char *ft_get_unit_string(PyObject *obj) {
    int len;
    char *str1, *str2;
    PyObject *t1, *t2;
    
    if (!PyObject_TypeCheck(obj, ft_gv_labrad_units_WithUnit)) return NULL;
    
    t1 = PyObject_GetAttrString(obj, "unit");
    t2 = PyObject_GetAttrString(t1, "name");
    str1 = ((PyStringObject *)t2)->ob_sval;
    len = PyString_GET_SIZE(t2);
    str2 = (char *)malloc((len+1)*sizeof(char));
    strcpy(str2, str1);
    Py_DECREF(t2);
    Py_DECREF(t1);
    
    return str2;
}

// END FRESH START -------------------------------------------------


// the following is a simplification of the real numpy PyArrayObject, use with caution
typedef struct PyArrayObject {
    PyObject_HEAD
    char *data;
    int nd;
    int *dimensions;
    int *strides;
    PyObject *base;
    void *descr;
    int flags;
    PyObject *weakreflist;
} PyArrayObject;

int ft_is_LRTime(PyObject *o);
int ft_is_list(PyObject *o);
int ft_is_tuple(PyObject *o);
int ft_is_string(PyObject *o);
int ft_is_bool(PyObject *o);
int ft_is_int32(PyObject *o);
int ft_is_uint32(PyObject *o);
int ft_is_float(PyObject *o);
int ft_is_complex(PyObject *o);
int ft_is_ValueWithUnit(PyObject *o, char *unit);
int ft_is_ComplexWithUnit(PyObject *o, char *unit);
int ft_is_ValueArray(PyObject *o, char *unit);
int ft_is_ComplexArray(PyObject *o, char *unit);
int ft_is_ndarray(PyObject *o);

// module initialization functions (called during first ft_flatten or ft_unflatten)

// functions supporting ft_flatten
int ft_size(PyObject *o);
char *ft_create_unambiguous_type_string(PyObject *o, int *len_ptr);
char *ft_create_type_string(PyObject *o, int *len_ptr);
int ft_find_beginning_next_type_token(char *str, int i);
int ft_type_strings_equivalent(char *str1, int len1, char *str2, int len2);
int ft_write_to_buf(PyObject *o, char *buf);
char *ft_append(char *str1, int *len1_ptr, char *str2, int len2);
int ft_verify_long_ints_nonnegative(PyObject *o, char *str);
void ft_reverse_memcpy(void *dest, void *src, int len);
void ft_appropriate_memcpy(void *dest, void *src, int len);
PyObject *ft_create_empty_PyStringObject(int size);
PyObject *ft_flatten_no_parse(PyObject *o);
// PyObject *ft_flatten(PyObject *self, PyObject *args);

// functions supporting ft_unflatten
PyObject *ft_build_Value(PyObject *o, char *t, int *ti_ptr);
PyObject *ft_unflatten_no_parse(char *s, int *si_ptr, char *t, int *ti_ptr);
PyObject *ft_unflatten_partial_parse(PyObject *o);
PyObject *ft_unflatten(PyObject *self, PyObject *args);

// test function: verifies o_i == unflatten(flatten(o_i)) for all o_i in [o_1, ..., o_n]
PyObject *ft_test(PyObject *self, PyObject *args);
PyObject *ft_make(PyObject *self, PyObject *args);

// This function calculates the flattened size of a python object, and determines if it is built out of supported types.
int ft_size(PyObject *o) {
    int i, n, size = 0, val;
    PyObject *t;
    PyArrayObject *a;
    
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
        if (PyObject_TypeCheck(o, ft_gv_labrad_units_ValueArray)) {
            // size = FIXED_FLOAT_SIZE;
            //printf("ValueArray\n");
            t = PyObject_GetAttrString(o, "_value");
            a = (PyArrayObject *)t;
            n = a->nd;
            // printf("%d\n", n);
            size = 1;
            for (i=0; i<n; i++) {
                size *= a->dimensions[i];
            }
            size *= a->strides[n-1];
            // printf("%d\n", size);
            size += FIXED_INT_SIZE;
            
            Py_DECREF(t);
            
            // PyErr_SetString(PyExc_TypeError, "Unsupported data type.");
            // goto exception;
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
            str1 = ft_append(str1, &len1, "_", 1);
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
            if (str1[j] == '?') str1[j] = '_';
        }
    }
        
    *len_ptr = len1;
    return str1;
    
exception:

    return NULL;
}

char *ft_create_type_string(PyObject *o, int *len_ptr) {
    int i, n, len1, len2;
    char *str1, *str2;
    PyObject *t, *t2;
    PyArrayObject *a;
    
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
        else if (PyObject_TypeCheck(o, ft_gv_labrad_units_ValueArray)) {
            t = PyObject_GetAttrString(o, "_value");
            a = (PyArrayObject *)t;
            n = a->strides[a->nd - 1];
            Py_DECREF(t);
            
            if (n == FIXED_FLOAT_SIZE) {
                str1 = ft_append(str1, &len1, "*v[", 3);
            }
            else if (n == FIXED_COMPLEX_SIZE) {
                str1 = ft_append(str1, &len1, "*c[", 3);
            }
            else {
                goto exception;
            }
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
        // printf("\n");
    }
    else {
        goto exception;
    }

    *len_ptr = len1;
    return str1;
    
exception:

    if (str1 != NULL) free(str1);
    assert(str2 == NULL);
    
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

char *ft_append(char *str1, int *len1_ptr, char *str2, int len2) {
    int total = *len1_ptr + len2;
    
    str1 = (char *)realloc(str1, total);
    memcpy(str1 + *len1_ptr, str2, len2);
    *len1_ptr = total;
    
    return str1;
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

void ft_reverse_memcpy(void *dest, void *src, int len) {
    int i;
    char *cdest, *csrc;
    
    cdest = (char *)dest;
    csrc = (char *)src;
    
    for (i=0; i<len; i++) cdest[i] = csrc[len-1-i];
}

void ft_appropriate_memcpy(void *dest, void *src, int len) {
    if (ft_gv_system_big_endian == FALSE) ft_reverse_memcpy(dest, src, len);
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
    // else if (so != NULL) Py_DECREF(so);
    
    return NULL;
}

/*
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
    PyObject *tc_mod, *tc_list, *tc_i, *tc_i_flat, *tc_i_pyflat, *tc_i_unflat, *tc_i_pyunflat;

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
        tc_i = tc_i_flat = tc_i_unflat = tc_i_pyflat = tc_i_pyunflat = NULL;
        printf("%d\n", i);
        tc_i = PyList_GET_ITEM(tc_list, i);

        if (PyErr_Occurred() != NULL) printf("Python exception 0\n");

        if (tc_i != NULL) {
            if (PyErr_Occurred() != NULL) printf("Python exception a\n");
            
            printf("fasttypes:\n");
            PyObject_Print(tc_i, stdout, Py_PRINT_RAW);
            printf("\n");

            if (PyErr_Occurred() != NULL) printf("Python exception b\n");
            
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

            if (PyErr_Occurred() != NULL) printf("Python exception c\n");
            
            printf("types:\n");
            tc_i_pyflat = PyObject_CallMethod(ft_gv_labrad_types, "flatten", "O", tc_i);
            if (tc_i_pyflat != NULL) {
                PyObject_Print(tc_i_pyflat, stdout, Py_PRINT_RAW);
                printf("\n");
                PyObject_Print(PyTuple_GET_ITEM(tc_i_pyflat, 1), stdout, Py_PRINT_RAW);
                printf("\n");
                tc_i_pyunflat = PyObject_CallMethod(ft_gv_labrad_types, "unflatten", "OO", PyTuple_GET_ITEM(tc_i_pyflat, 0), PyTuple_GET_ITEM(tc_i_pyflat, 1));
                if (tc_i_pyunflat != NULL) {
                    PyObject_Print(tc_i_pyunflat, stdout, Py_PRINT_RAW);
                    printf("\n");
                }
            }

            /*
            tc_i_pyflat = PyObject_CallMethod(ft_gv_labrad_types, "flatten", "O", tc_i);
            if (tc_i_pyflat != NULL) {
                printf("(");
                // PyObject_Print(PyTuple_GET_ITEM(tc_i_pyflat, 0), stdout, Py_PRINT_RAW);
                PyObject_Print(PyTuple_GET_ITEM(tc_i_pyflat, 0), stdout, 0);
                printf(", ");
                PyObject_Print(PyTuple_GET_ITEM(tc_i_pyflat, 1), stdout, Py_PRINT_RAW);
                printf(")\n");
                tc_i_pyunflat = PyObject_CallMethod(ft_gv_labrad_types, "unflatten", "OO", PyTuple_GET_ITEM(tc_i_pyflat, 0), PyTuple_GET_ITEM(tc_i_pyflat, 1));
                if (tc_i_pyunflat != NULL) {
                    // PyObject_Print(tc_i_pyunflat, stdout, Py_PRINT_RAW);
                    // printf("\n");
                }
            }
            */
            
            if (PyErr_Occurred() != NULL) printf("Python exception d\n");
        }
        
        if (PyErr_Occurred() != NULL) printf("Python exception 1\n");
        
        if (tc_i_flat == NULL || tc_i_unflat == NULL || PyObject_RichCompareBool(tc_i, tc_i_unflat, Py_EQ) != 1) {
            printf("ERROR: fasttypes pass case %d failed\n", i);
            /*
            PyObject_Print(tc_i, stdout, Py_PRINT_RAW);
            printf("\n");
            PyObject_Print(tc_i_unflat, stdout, Py_PRINT_RAW);
            printf("\n");
            */
            if (PyErr_Occurred() != NULL) {
                printf("Python exception during compare\n");
                PyErr_Clear();
            }
            // if (PyErr_Occurred() != NULL) printf("Python exception ft\n");
            flag = FALSE;
        }
        if (tc_i_pyflat == NULL || tc_i_pyunflat == NULL || PyObject_RichCompareBool(tc_i, tc_i_pyunflat, Py_EQ) != 1) {
            printf("ERROR: types pass case %d failed\n", i);
            if (PyErr_Occurred() != NULL) {
                printf("Python exception during compare\n");
                PyErr_Clear();
            }
            // if (PyErr_Occurred() != NULL) printf("Python exception t\n");
            flag = FALSE;
        }
        if (tc_i_flat == NULL || tc_i_pyflat == NULL || PyObject_RichCompareBool(PyTuple_GET_ITEM(tc_i_flat, 0), PyTuple_GET_ITEM(tc_i_pyflat, 0), Py_EQ) != 1) {
            printf("ERROR: fasttypes and types flattened stings do not match\n", i);
            if (PyErr_Occurred() != NULL) {
                printf("Python exception during compare\n");
                PyErr_Clear();
            }
            flag = FALSE;
        }
        printf("\n");

        if (tc_i_flat != NULL) Py_DECREF(tc_i_flat);
        if (tc_i_unflat != NULL) Py_DECREF(tc_i_unflat);
        if (tc_i_pyflat != NULL) Py_DECREF(tc_i_pyflat);
        if (tc_i_pyunflat != NULL) Py_DECREF(tc_i_pyunflat);

        if (PyErr_Occurred() != NULL) printf("Python exception 3\n");
    }
    
    Py_DECREF(tc_list);
    
    tc_list = PyObject_GetAttrString(tc_mod, "failcases");
    if (tc_list == NULL || !PyList_Check(tc_list)) goto exception;
    
    n = PyList_GET_SIZE(tc_list);
    // flag = TRUE;
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
    else printf("Some test cases had unexpected behavior,\n");
    
    Py_DECREF(tc_list);
    Py_DECREF(tc_mod);
    
    Py_INCREF(Py_None);
    return Py_None;
    
exception:

    if (tc_list != NULL) Py_DECREF(tc_list);
    if (tc_mod != NULL) Py_DECREF(tc_mod);

    return NULL;
}

PyObject *ft_make(PyObject *self, PyObject *args) {
    int i, nd, *dims, nelems, *strides;
    double *data;
    PyObject *o;
    
    if (!ft_gv_initialized) {
        if (ft_initialize() == EXCEPTION_RAISED) goto exception;
    }

    PyArg_ParseTuple(args, "O", &o);
    // if (PyObject_TypeCheck(o, ft_gv_labrad_units_Value)) printf("labRAD Value\n");

    o = PyObject_CallMethod(ft_gv_numpy, "eye", "ii", 4, 4);
    
    nd = ((PyArrayObject *)o)->nd;
    printf("nd: %d\n", nd);
    
    dims = ((PyArrayObject *)o)->dimensions;
    nelems = 1;
    for (i=0; i<nd; i++) {
        printf("%d\n", dims[i]);
        nelems *= dims[i];
    }
    
    strides = ((PyArrayObject *)o)->strides;
    for (i=0; i<nd; i++) printf("%d\n", strides[i]);
    
    data = (double *)(((PyArrayObject *)o)->data);
    for (i=0; i<nelems; i++) printf("%g\n", data[i]);
    
    return o;

exception:

    return NULL;
}

static PyMethodDef fasttypes_methods[] = {
    {"flatten", (PyCFunction)ft_flatten, METH_VARARGS | METH_KEYWORDS, "flatten() doc string."},
    {"unflatten", ft_unflatten, METH_VARARGS, "unflatten() doc string."},
    {"test", ft_test, METH_VARARGS, "test() doc string."},
    {"make", ft_make, METH_VARARGS, "make() doc string."},
    {NULL, NULL}
};

PyMODINIT_FUNC initfasttypes(void) {
    Py_InitModule("fasttypes", fasttypes_methods);
}