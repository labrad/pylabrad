#include <Python.h>
#include <structmember.h>
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <numpy/arrayobject.h>
#include <stdio.h>
#include <string.h>
/*
 * Unit dictionary type.  This is the guts of the unit implementaiton,
 * and fills the same purpose as the NumberDict class used in the
 * python implementation.  This implementation is based on arrays, not
 * dictionaries.
 */


typedef struct {
    PyObject *name;
    int numer, denom;
} UnitName;

typedef struct {
    PyObject_VAR_HEAD
    UnitName data[0];
} UnitArray;

static UnitArray *dimensionless=0;

/* factor_t will be used to implement units who ratio doesn't 
   fit the standard numer/denom * 10^exp10 format.  For instance,
   physical quantity based units like eV have experimentally determined
   values while the radian -> degree ratio is irrational. factor_t
   solves that by giving "denom=0" a special meaning, that the
   numerator contains a floating point ratio.  exp10 is still used
   to allow units like MeV to be represented cleanly.
*/
  
typedef struct {
    union {
	long long numer;
	double ratio;
    };
    long long denom;
    int exp_10;
} factor_t;

/* 
 * C representation of a value
 */

typedef struct {
    PyObject_HEAD
    PyObject *value;
    factor_t unit_factor;
    UnitArray *base_units;
    UnitArray *display_units;
} WithUnitObject;

static long long iroot(long long x, int y);
static long long ipow(long long x, int y);

static PyObject *unit_array_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *unit_array_repr(UnitArray *obj);
static PyObject *unit_array_op(UnitArray *left, UnitArray *right, int sign_r);
static PyObject *unit_array_mul(PyObject *a, PyObject *b);
static PyObject *unit_array_div(PyObject *a, PyObject *b);

static PyObject *module=0;
static PyObject *unit_cache=0;
static PyObject *UnitMismatchError;

static PyTypeObject UnitArrayType;
static PyTypeObject WithUnitType;
static PyTypeObject ValueType;
static PyTypeObject ComplexType;
static PyTypeObject ValueArrayType;

static PyObject *value_str(WithUnitObject *obj);

static void
least_terms(int *a, int *b)
{
    int x=*a, y=*b, z;
    if (x==0) {
	*b = 1;
	return;
    }
    for(;;) {
	z = x%y;
	if (z==1) {
	    if (*b < 0) {
		*a = -*a;
		*b = -*b;
		return;
	    }
	}
	if (z==0) {
	    if ((y<0) ^ (*b<0)) // Make sure denominator is positive
		y = -y;
	    *a /= y;
	    *b /= y;
	    return;
	}
	x = y;
	y = z;
    }
}

static long long gcd(long long a, long long b);

static PyObject *
unit_array_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    UnitArray *self;
    PyObject *name;
    static char *kwlist[] = {"name", "numer", "denom", 0};
    int rv;
    int numer=1, denom=1;

    rv = PyArg_ParseTupleAndKeywords(args, kwds, "S|ii", kwlist, 
				     &name, &numer, &denom);
    if (!rv)
	return 0;
    if (denom==0) {
	PyErr_SetString(PyExc_ValueError, "Denominator cannot be zero");
	return 0;
    }
    if (denom < 0) {
	denom = -denom;
	numer = -numer;
    }
    least_terms(&numer, &denom);
    self = (UnitArray *)type->tp_alloc(type, 1);
    if (self != NULL) {
	self->ob_size = 1;
	self->data[0].name = name;
	self->data[0].numer = numer;
	self->data[0].denom = denom;
	Py_INCREF(self->data[0].name);
    }
    return (PyObject *)self;
}

static PyObject *
unit_array_str(UnitArray *obj)
{
    PyObject *result;
    PyObject *tmp;
    char *name, *prefix;
    int i, first=1;

    if(obj->ob_size == 0) {
	result = PyString_FromString("");
	return result;
    }
    result = PyString_FromString("");
    if(!result)
	return 0;

    for(i=0; i<obj->ob_size; i++) {
	if (obj->data[i].numer < 0)
	    continue;
	if(first)
	    prefix = "";
	else
	    prefix = "*";
	first = 0;
	name = PyString_AsString(obj->data[i].name);
	if (obj->data[i].numer == 1 && obj->data[i].denom == 1)
	    tmp = PyString_FromFormat("%s%s", prefix, name);
	else if(obj->data[i].denom == 1)
	    tmp = PyString_FromFormat("%s%s^%d", prefix, name, obj->data[i].numer);
	else
	    tmp = PyString_FromFormat("%s%s^(%d/%d)", prefix, name, obj->data[i].numer, obj->data[i].denom);
	if(!tmp) {
	    Py_DECREF(result);
	    return 0;
	}
	PyString_ConcatAndDel(&result, tmp);
	if(!result)
	    return 0;
    }

    for(i=0; i<obj->ob_size; i++) {
	if (obj->data[i].numer > 0)
	    continue;
	if (first)
	    prefix = "1/";
	else
	    prefix = "/";
	first = 0;

	name = PyString_AsString(obj->data[i].name);
	if (obj->data[i].numer == -1 && obj->data[i].denom == 1)
	    tmp = PyString_FromFormat("%s%s", prefix, name);
	else if(obj->data[i].denom == 1)
	    tmp = PyString_FromFormat("%s%s^%d", prefix, name, -obj->data[i].numer);
	else
	    tmp = PyString_FromFormat("%s%s^(%d/%d)", prefix, name, -obj->data[i].numer, obj->data[i].denom);
	if(!tmp) {
	    Py_DECREF(result);
	    return 0;
	}
	PyString_ConcatAndDel(&result, tmp);
	if(!result)
	    return 0;
    }
    return result;
}

static PyObject *
unit_array_repr(UnitArray *obj)
{
    PyObject *str_rep;
    PyObject *result;

    str_rep = unit_array_str(obj);
    if(!str_rep)
	return 0;
    result = PyString_FromFormat("UnitArray(\"%s\")", PyString_AsString(str_rep));
    Py_DECREF(str_rep);
    return result;
}

static PyObject *
unit_array_richcompare(PyObject *a, PyObject *b, int op)
{
    UnitArray *left, *right;
    int result=0;
    int i=0;

    if(!PyObject_IsInstance(a, (PyObject *)&UnitArrayType) || !PyObject_IsInstance(b, (PyObject *)&UnitArrayType)) {
	Py_INCREF(Py_NotImplemented);
	PyErr_Clear();
	return Py_NotImplemented;
    }
    if (op != Py_EQ && op != Py_NE) {
	PyErr_SetString(PyExc_TypeError, "Can't compare unit arrays except for equality");
	return 0;
    }
    left = (UnitArray *)a;
    right = (UnitArray *)b;
    if (left->ob_size == right->ob_size) {
	for (i=0; i<left->ob_size; i++) {
	    if (PyObject_RichCompareBool(left->data[i].name, right->data[i].name, Py_NE))
		break;
	    if (left->data[i].numer != right->data[i].numer)
		break;
	    if (left->data[i].denom != right->data[i].denom)
		break;
	}
	if (i == left->ob_size)
	    result = 1;
    }
    if ((op == Py_EQ && result) || (op == Py_NE && !result))
	Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *
unit_array_div(PyObject *a, PyObject *b)
{
    if(!PyObject_IsInstance(a, (PyObject *)&UnitArrayType) || ! PyObject_IsInstance(b, (PyObject *)&UnitArrayType)) {
	Py_INCREF(Py_NotImplemented);
	PyErr_Clear();
	return Py_NotImplemented;
    }
    return unit_array_op((UnitArray *) a, (UnitArray *)b, -1);
}

static PyObject *
unit_array_mul(PyObject *a, PyObject *b)
{
    if(!PyObject_IsInstance(a, (PyObject *)&UnitArrayType) || ! PyObject_IsInstance(b, (PyObject *)&UnitArrayType)) {
	Py_INCREF(Py_NotImplemented);
	PyErr_Clear();
	return Py_NotImplemented;
    }
    return unit_array_op((UnitArray *) a, (UnitArray *)b, 1);
}

static PyObject *
unit_array_op(UnitArray *left, UnitArray *right, int sign_r)
{
    int idx_l=0, idx_r=0, idx_out=0, new_numer, new_denom;
    int cmp_val;

    UnitArray *out;
    // Compute the needed array size
    while(idx_l < left->ob_size || idx_r < right->ob_size) {
	if (idx_l == left->ob_size)
	    cmp_val = 1;
	else if (idx_r == right->ob_size)
	    cmp_val = -1;
	else
	    cmp_val = strcmp(PyString_AsString(left->data[idx_l].name), PyString_AsString(right->data[idx_r].name));
	if (cmp_val < 0)
	    idx_l += 1;
	if (cmp_val > 0)
	    idx_r += 1;
	if (cmp_val == 0) {
	    new_numer = left->data[idx_l].numer * right->data[idx_r].denom + sign_r * right->data[idx_r].numer * left->data[idx_l].denom;
	    if(!new_numer)
		idx_out -= 1;
	    idx_l++;
	    idx_r++;
	}
	idx_out += 1;
    }
    out =  (UnitArray *)(&UnitArrayType)->tp_alloc(&UnitArrayType, idx_out);

    if (!out)
	return 0;
    idx_l = idx_r = idx_out = 0;
    while(idx_l < left->ob_size || idx_r < right->ob_size) {
	if (idx_l == left->ob_size)
	    cmp_val = 1;
	else if (idx_r == right->ob_size)
	    cmp_val = -1;
	else {
	    cmp_val = strcmp(PyString_AsString(left->data[idx_l].name), PyString_AsString(right->data[idx_r].name));
	}
	if (cmp_val < 0) {
	    out->data[idx_out].name = left->data[idx_l].name;
	    out->data[idx_out].numer = left->data[idx_l].numer;
	    out->data[idx_out].denom = left->data[idx_l].denom;
	    Py_INCREF(out->data[idx_out].name);
	    idx_out++;
	    idx_l++;
	}
	if (cmp_val > 0) {
	    out->data[idx_out].name = right->data[idx_r].name;
	    out->data[idx_out].numer = sign_r * right->data[idx_r].numer;
	    out->data[idx_out].denom = right->data[idx_r].denom;
	    Py_INCREF(out->data[idx_out].name);
	    idx_out++;
	    idx_r++;
	}
	if (cmp_val == 0) {
	    new_numer = left->data[idx_l].numer * right->data[idx_r].denom + sign_r * right->data[idx_r].numer * left->data[idx_l].denom;
	    if (new_numer) {
		out->data[idx_out].name = left->data[idx_l].name;
		new_denom = left->data[idx_l].denom * right->data[idx_r].denom;
		least_terms(&new_numer, &new_denom);
		out->data[idx_out].numer = new_numer;
		out->data[idx_out].denom = new_denom;
		Py_INCREF(out->data[idx_out].name);
		idx_out++;
	    }
	    idx_l++;
	    idx_r++;
	}
    }
    out->ob_size = idx_out;
    return (PyObject *)out;
}

/* Compute rational power
 * Takes an input PyObject that should be either an integer or float, and converts it to a rational number a/b.
 * 
 * This works for simple fractions including 1/2, 1/3, and 1/4 that might be used as powers for units
 * such as V/Hz**.5.
 */
static int
rational_power(PyObject *a, long *numer, long *denom)
{
    double d;
    int x;

    if (PyObject_IsInstance(a,(PyObject *) &PyInt_Type)) {
	*numer = PyInt_AsLong(a);
	*denom = 1;
	return 1;
    }
    d = PyFloat_AsDouble(a);
    if (d==-1.0 && PyErr_Occurred()) 
	return 0;
    x = floor(12*d + 0.5);
    if ( fabs(12*d - x) < 1e-5 ) {
	long tmp = gcd(12, x);
	*numer = x/tmp;
	*denom = 12/tmp;
	
	return 1;
    }
    PyErr_SetString(PyExc_ValueError, "power can't be converted to simple fraction (N/12)");
    return 0;
}

static
UnitArray *
unit_array_pow_frac(UnitArray *obj, int numer, int denom)
{
    UnitArray *result;
    int idx;

    result =  (UnitArray *)(&UnitArrayType)->tp_alloc(&UnitArrayType, obj->ob_size);
    result->ob_size = obj->ob_size;
    for (idx=0; idx<obj->ob_size; idx++) {
	int new_numer, new_denom;

	result->data[idx].name = obj->data[idx].name;
	Py_INCREF(result->data[idx].name);
	new_numer = obj->data[idx].numer * numer;
	new_denom = obj->data[idx].denom * denom;
	least_terms(&new_numer, &new_denom);
	result->data[idx].numer = new_numer;
	result->data[idx].denom = new_denom;
    }
    return result;
}

static
PyObject *
unit_array_pow(PyObject *a, PyObject *b, PyObject *c)
{
    long numer, denom;

    if (c != Py_None) {
	PyErr_SetString(PyExc_ValueError, "WithUnit power does not support third argument");
	return 0;
    }

    if(!PyObject_IsInstance(a, (PyObject *)&UnitArrayType)) {
	PyErr_SetString(PyExc_TypeError, "UnitArray __pow__() requires left argument to be UnitArray");
	return 0;
    }
    if (!rational_power(b, &numer, &denom))
	return 0;
    return (PyObject *)unit_array_pow_frac((UnitArray *)a, numer, denom);
}

static void
unit_array_dealloc(UnitArray *self)
{
    int idx;
    for(idx=0; idx<self->ob_size; idx++) {
	Py_XDECREF(self->data[idx].name);
    }
    self->ob_type->tp_free((PyObject *)self);
}

static PyNumberMethods UnitArrayNumberMethods = {
    0,			/* nb_add */
    0,			/* nb_subtract */
    unit_array_mul,    	/* nb_multiply */
    unit_array_div,    	/* nb_divide */
    0,		       	/* nb_remainder */
    0,		       	/* nb_divmod */
    unit_array_pow,	/* nb_power */
    0,     	        /* nb_negative */
    0,               	/* nb_positive */
    0,      	        /* nb_absolute */
    0,	       	        /* nb_nonzero (Used by PyObject_IsTrue) */
    0			/* nb_invert */
};

static PyTypeObject UnitArrayType = {
    PyObject_HEAD_INIT(NULL) 
    0,			       /* ob_size */
    "UnitArray",	       /* tp_name */
    sizeof(UnitArray),         /*tp_basicsize*/
    sizeof(UnitName),          /*tp_itemsize*/
    (destructor)unit_array_dealloc, /*tp_dealloc*/
    0,                         /*tp_print*/
    0,                         /*tp_getattr*/
    0,                         /*tp_setattr*/
    0,                         /*tp_compare*/
    (reprfunc)unit_array_repr, /*tp_repr*/
    &UnitArrayNumberMethods,   /*tp_as_number*/
    0,                         /*tp_as_sequence*/
    0,                         /*tp_as_mapping*/
    0,                         /*tp_hash */
    0,                         /*tp_call*/
    (reprfunc)unit_array_str,  /*tp_str*/
    0,                         /*tp_getattro*/
    0,                         /*tp_setattro*/
    0,                         /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT|Py_TPFLAGS_CHECKTYPES,        /*tp_flags*/
    "Unit Array object",       /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    unit_array_richcompare,    /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    0,		               /* tp_methods */
    0,	                       /* tp_members */
    0,                         /* tp_getset */
    0,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,                         /* tp_init */
    0,                         /* tp_alloc */
    unit_array_new             /* tp_new */
};

/* This is the only method that creates new value objects.  It is
 * responsible for maintaining invariants like the unit factor being
 * in lowest terms and making sure that value is an appropriate type.
 * If we decide to use separate types for Value, Complex, and ValueArray
 * this function will figure out the right type.
 */
static WithUnitObject *
value_create(PyObject *data, factor_t factor, UnitArray *base_units, UnitArray *display_units)
{
    double tmp;
    PyObject *val;
    WithUnitObject *result;
    PyTypeObject *target_type;

    if(!data) /* This generally means something generated an exception previously. */
	return 0;
    if (PyFloat_Check(data)) {
	val = data;
	target_type = &ValueType;
	Py_INCREF(val);
    } else if (PyComplex_Check(data)) {
	val = data;
	target_type = &ComplexType;
	Py_INCREF(val);
    } else if (PyArray_Check(data)) {
	val = data;
	target_type = &ValueArrayType;
	Py_INCREF(val);
    } else {
	tmp = PyFloat_AsDouble(data);
	if (tmp==-1 && PyErr_Occurred())
	    return 0;
	val = PyFloat_FromDouble(tmp);
	target_type = &ValueType;
    }
    result = (WithUnitObject *)WithUnitType.tp_alloc(target_type, 0);
    if (!result) {
	Py_DECREF(val);
	return 0;
    }
    result->value = val;
    result->unit_factor = factor;
    result->base_units = base_units;
    result->display_units = display_units;
    Py_INCREF(result->base_units);
    Py_INCREF(result->display_units);
    return result;
}


/*
 * Used by binary operators for coercion.  If the given object is a
 * Value, call Py_INCREF and return it.  Otherwise, convert to float,
 * and construct a temporary object with refcount 1 and dimensionless
 * units.
 */
static WithUnitObject *
value_wrap(PyObject *obj)
{
    WithUnitObject *result;
    factor_t unit_factor = {{1}, 1, 0};

    if (PyObject_IsInstance(obj, (PyObject *)&WithUnitType)) {
	Py_INCREF(obj);
	return (WithUnitObject *)obj;
    }
    result = value_create(obj, unit_factor, dimensionless, dimensionless);
    return result;
}

/*
  This helper function accepts either a string unit name or a unit object
  and returns a value of '1' with the appropriate units.  Use cases are
  __getitem__, inUnitsOf, and new value construction.

  Because this can be performance sensitive, we try to stay in C as much
  as possible.  The fastest case will be to pass in a unit object.  We
  can also do string lookups in the unit cache relatively quickly.  The
  slow case for unit strings that are not already in the cache, which
  requires calling up to python.
 */
static WithUnitObject *
lookup_unit_val(PyObject *unit_obj)
{
    PyObject *unit;
    PyObject *unit_val=0;

    if (PyString_Check(unit_obj)) {
	unit = PyObject_GetItem(unit_cache, unit_obj);
	if(!unit) {
	    PyErr_Clear();
	    unit = PyObject_CallMethod(module, "_unit_from_str", "O", unit_obj);
	    if (!unit)
		return 0;
	}
    }
    else {
	unit = unit_obj;
	Py_INCREF(unit);
    }
    unit_val = PyObject_GetAttrString(unit, "_value"); /* For Unit objects */
    Py_DECREF(unit);
    if(!unit_val || !PyObject_IsInstance(unit_val, (PyObject *)&WithUnitType)) {
	Py_XDECREF(unit_val);
	PyErr_SetString(PyExc_TypeError, "Expected Unit or string");
	return 0;
    }
    return (WithUnitObject *)unit_val;
}
static PyObject *
value_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyObject *val, *unit=0, *unit_val=0, *result;
    char *kwlist[] = {"number", "unit", 0};
    int rv;

    rv = PyArg_ParseTupleAndKeywords(args, kwds, "O|O", kwlist, &val, &unit);

    if(!rv)
	return 0;
    if(!unit)
	return (PyObject *)value_wrap(val);

    unit_val = (PyObject *)lookup_unit_val(unit);

    if (PyList_Check(val)) 
	val = PyArray_EnsureArray(val);
    else
	Py_INCREF(val);    

    if(!unit_val || !val) {
	Py_XDECREF(unit_val);
	Py_XDECREF(val);
	return 0;
    }
    result = PyNumber_Multiply(val, unit_val);
    Py_XDECREF(val);
    Py_XDECREF(unit_val);
    return result;
}

/*
 * Python interface to value_create.
 */
static PyObject *
value_new_raw(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyObject *value=0, *numer_obj;
    long long numer=1, denom=1;
    int overflow;
    double float_ratio=0;
    int exp_10=0;
    factor_t unit_factor;
    int rv;
    UnitArray *base_units=dimensionless, *display_units=dimensionless;
    WithUnitObject *obj;
    //char *kwlist[] = {"value", "factor", "exp10", "base_units", "display_units", 0};
    char *kwlist[] = {"value", "numer", "denom", "exp10", "base_units", "display_units", 0};

    rv = PyArg_ParseTupleAndKeywords(args, kwds, "O|OLiOO", kwlist, 
				     &value, &numer_obj, &denom, &exp_10, &base_units, &display_units);
    if (!rv) 
	return 0;


    if (PyInt_Check(numer_obj)) {
	numer = PyInt_AsLong(numer_obj);
	float_ratio = 0;
    } else if (PyLong_Check(numer_obj)) {
	float_ratio = 0;
	numer = PyLong_AsLongLongAndOverflow(numer_obj, &overflow);
	if (overflow) {
	    numer = 0;
	    float_ratio = PyLong_AsDouble(numer_obj);
	}
    } else if (PyFloat_Check(numer_obj)) {
	numer = 0;
	float_ratio = PyFloat_AsDouble(numer_obj);
    } else {
	PyErr_SetString(PyExc_TypeError, "Numerator must be either integer or floating point.");
	return 0;
    }
    
    if (float_ratio != 0 && (denom != 0)) {
	PyErr_SetString(PyExc_ValueError, "Cannot specify both float_ratio and numer/denom");
	return 0;
    }

    if(!PyObject_IsInstance((PyObject *)base_units, (PyObject *)&UnitArrayType) || !PyObject_IsInstance((PyObject *)display_units, (PyObject *)&UnitArrayType) ) {
	PyErr_SetString(PyExc_TypeError, "Base names and display names must be UnitArray objects");
	return 0;
    }
    if(float_ratio) {
	unit_factor.ratio = float_ratio;
	unit_factor.denom = 0;
    }
    else {
	unit_factor.numer = numer;
	unit_factor.denom = denom;
    }
    unit_factor.exp_10 = exp_10;
    obj = value_create(value, unit_factor, base_units, display_units);
    return (PyObject *)obj;
}

static void
value_dealloc(WithUnitObject *obj)
{
    Py_CLEAR(obj->value);
    Py_XDECREF(obj->base_units);
    Py_XDECREF(obj->display_units);
    obj->ob_type->tp_free((PyObject *)obj);
}

static
WithUnitObject *
value_neg(WithUnitObject *obj)
{
    WithUnitObject *result=0;
    PyObject *tmp;

    tmp = PyNumber_Negative((PyObject *)obj->value);

    if (tmp)
	result = value_create(tmp, obj->unit_factor, obj->base_units, obj->display_units);
    Py_XDECREF(tmp);
    return result;
}

static
PyObject *
value_pos(PyObject *obj)
{
    Py_INCREF(obj);
    return obj;
}

static
WithUnitObject *
value_abs(WithUnitObject *obj)
{
    WithUnitObject *new_obj=0;
    PyObject *new_val = PyNumber_Absolute(obj->value);
    if(new_val)
	new_obj = value_create(new_val, obj->unit_factor, obj->base_units, obj->display_units);
    Py_XDECREF(new_val);
    return new_obj;
}

static
int
value_nz(WithUnitObject *obj)
{
    return PyObject_IsTrue(obj->value);
}

static
long long
gcd(long long a, long long b)
{
    if (a==0) return b;
    return gcd(b%a, a);
}

static
PyObject *
ax_plus_b(PyObject *a, double x, PyObject *b)
{
    PyObject *factor, *prod, *sum;

    factor = PyFloat_FromDouble(x);
    if(!factor)
	return 0;
    prod = PyNumber_Multiply(factor, a);
    if (!prod) {
	Py_DECREF(factor);
	return 0;
    }
    sum = PyNumber_Add(prod, b);
    Py_DECREF(prod);
    Py_DECREF(factor);
    return sum;
}

static
double
exp10_int(int x)
{
    int i, invert;
    double result= 1.0;
    invert = x<0;
    if (invert)
	x = -x;
    for (i=0; i<x; i++)
	result = result * 10.0;
    if (invert)
	result = 1.0/result;
    return result;
}
/*
 * The following functions manipulate factor_t objects.  This hides
 * the ugly special casing of the float vs. rational representation
 * from the rest of the unit implementation.
 */
double factor_to_double(factor_t obj)
{
    if (obj.denom)
	return obj.numer * 1.0 / obj.denom * exp10_int(obj.exp_10);
    else
	return obj.ratio * exp10_int(obj.exp_10);
}

factor_t factor_mul(factor_t left, factor_t right)
{
    long long gcd1, gcd2;
    factor_t result;

    // If either input uses a floating point representation, or the
    // result would overflow, use a floating point output.
    if (left.denom == 0 || right.denom == 0 || 
	left.numer > 1LL<<32 || right.numer > 1LL<<32 || 
	left.denom > 1LL<<32 || right.denom > 1LL<<32) {
	result.denom = 0;
	if (left.denom)
	    result.ratio = left.numer * 1.0 / left.denom;
	else
	    result.ratio = left.ratio;
	if (right.denom)
	    result.ratio *= right.numer * 1.0 / right.denom;
	else
	    result.ratio *= right.ratio;
	result.exp_10 = left.exp_10 + right.exp_10;
	return result;
    }
    gcd1 = gcd(left.numer, right.denom);
    gcd2 = gcd(right.numer, left.denom);

    result.numer = (left.numer/gcd1) * (right.numer/gcd2);
    result.denom = (left.denom/gcd2) * (right.denom/gcd1);
    result.exp_10 = left.exp_10 + right.exp_10;
    return result;
}

factor_t factor_ratio(factor_t left, factor_t right)
{
    factor_t result;
    long long gcd1, gcd2;

    // If either input uses a floating point representation, or the
    // result would overflow, use a floating point output.
    if (left.denom == 0 || right.denom == 0 || 
	left.numer > (1LL<<32) || right.numer > (1LL<<32) || 
	left.denom > (1LL<<32) || right.denom > (1LL<<32)) {
	result.denom = 0;
	if (left.denom)
	    result.ratio = left.numer * 1.0 / left.denom;
	else
	    result.ratio = left.ratio;
	if (right.denom)
	    result.ratio *= right.denom * 1.0 / right.numer;
	else
	    result.ratio /= right.ratio;
	result.exp_10 = left.exp_10 - right.exp_10;
	return result;
    }
    gcd1 = gcd(left.numer, right.numer);
    gcd2 = gcd(right.denom, left.denom);

    result.numer = (left.numer/gcd1) * (right.denom/gcd2);
    result.denom = (left.denom/gcd2) * (right.numer/gcd1);
    result.exp_10 = left.exp_10 - right.exp_10;
    return result;
}

double factor_ratio_double(factor_t left, factor_t right)
{
    return factor_to_double(factor_ratio(left, right));
}

int factor_pow(factor_t base, int pow_numer, int pow_denom, factor_t *result)
{
    int pow_sign=1;

    if (pow_numer < 0) {
	pow_numer = -pow_numer;
	pow_sign = -1;
    }

    if ((base.exp_10 * pow_numer) % pow_denom) {
	PyErr_SetString(PyExc_RuntimeError, "Unable to take root of specified unit\n");
	return 0;
    }
    result->exp_10 = base.exp_10 * pow_sign * pow_numer / pow_denom;
    // If the input is a floating point ratio or the result would
    // overflow, return a floating point ratio
    if (base.denom == 0 || 
	(pow(base.numer, pow_numer) > 9.2e18) ||
	(pow(base.denom, pow_numer) > 9.2e18)) {

	double ratio;
	if (base.denom)
	    ratio = base.numer * 1.0 / base.denom;
	else
	    ratio = base.ratio;
	result->ratio = pow(ratio, pow_numer * pow_sign * 1.0 / pow_denom);
	result->denom = 0;
	return 1;
    }

    result->numer = iroot(base.numer, pow_denom);
    result->denom = iroot(base.denom, pow_denom);

    if(result->numer == 0 || result->denom == 0) {
	PyErr_SetString(PyExc_ValueError, "Unable to take root of specified unit\n");
	return 0;
    }
    result->numer = ipow(result->numer, pow_numer);
    result->denom = ipow(result->denom, pow_numer);

    if (pow_sign == -1) {
	long long tmp = result->numer;
	result->numer = result->denom;
	result->denom = tmp;
    }
    return 1;
}
/* The following are the basic arithmetic operators, +, -, *, and /.
 *
 * These operatiosn try to avoid unnecessary inexact math operations.
 * The unit proefactor is stored as an exact ratio.  The goal is that
 * if you have some program written using implicit units (whatever
 * they are), and you convert it to use explicit units, you should get
 * exactly the same result which wouldn't happen if we converted
 * internally to SI base units.  In addition when mixed-unit addition
 * converts to the lowest common denominator, we pick the "smaller"
 * unit.  1 ns + 1 s will be converted to 1000000001.0 ns regardless
 * of the operand order.
 */
static
PyObject *
value_add(PyObject *a, PyObject *b)
{
    WithUnitObject *left=0, *right=0, *result=0, *example=0;
    PyObject *new_value=0;
    double factor_l, factor_r;

    left = value_wrap(a);
    right = value_wrap(b);
    if(!left || !right) {
	PyErr_Clear();
	Py_XDECREF(left);
	Py_XDECREF(right);
	Py_INCREF(Py_NotImplemented);
	return Py_NotImplemented;
    }

    if(!PyObject_RichCompareBool((PyObject *)left->base_units, (PyObject *)right->base_units, Py_EQ)) {
	PyErr_SetString(UnitMismatchError, "WithUnit __add__ requires equivalent units");
	goto fail;
    }
    
    factor_l = factor_to_double(left->unit_factor);
    factor_r = factor_to_double(right->unit_factor);

    if (factor_l < factor_r) {
	factor_r = factor_ratio_double(right->unit_factor, left->unit_factor);
	new_value = ax_plus_b(right->value, factor_r, left->value);
	example = left;
    } 
    else {
	factor_l = factor_ratio_double(left->unit_factor, right->unit_factor);
	new_value = ax_plus_b(left->value, factor_l, right->value);
	example = right;
    }

    if(!new_value)
	goto fail;

    result = value_wrap(new_value);
    if (!result)
	goto fail;
    
    result->unit_factor = example->unit_factor;
    Py_DECREF(result->base_units);
    result->base_units = example->base_units;
    Py_INCREF(result->base_units);
    Py_DECREF(result->display_units);
    result->display_units = example->display_units;
    Py_INCREF(result->display_units);

    Py_XDECREF(left);
    Py_XDECREF(right);
    return (PyObject *)result;
 fail:
    if (!PyErr_Occurred())
	PyErr_SetString(PyExc_MemoryError, "value_add failed");
    Py_XDECREF(new_value);
    Py_XDECREF(left);
    Py_XDECREF(right);
    return 0;
}

/*
 * value_sub just converts to addition.  There is possibly some
 * performance to be gained here by avoiding creating an extra
 * temporary.
 */
static 
PyObject *
value_sub(PyObject *a, PyObject *b)
{
    PyObject *right, *result;
    right = PyNumber_Negative(b);
    if (!right) {
	Py_INCREF(Py_NotImplemented);
	PyErr_Clear();
	return Py_NotImplemented;
    }
    result = PyNumber_Add(a, right);
    Py_DECREF(right);
    return result;
}

/* 
 * Value_mul and value_div have the same structure, but they are
 * different enough that we don't bother factoring the common code.
 */
static 
PyObject *
value_mul(PyObject *a, PyObject *b)
{
    WithUnitObject *left, *right, *result;
    PyObject *val;
    factor_t result_factor;
    UnitArray *base_units, *display_units;

    left = value_wrap(a);
    right = value_wrap(b);
    if (!left || !right) {
	Py_XDECREF(left);
	Py_XDECREF(right);
	Py_INCREF(Py_NotImplemented);
	PyErr_Clear();
	return Py_NotImplemented;
    }
    val = PyNumber_Multiply(right->value, left->value);
    result_factor = factor_mul(left->unit_factor, right->unit_factor);
    base_units = (UnitArray *)PyNumber_Multiply((PyObject *)left->base_units, (PyObject *)right->base_units);
    display_units = (UnitArray *)PyNumber_Multiply((PyObject *)left->display_units, (PyObject *)right->display_units);
    if (val && base_units && display_units) {
	result = value_create(val, result_factor, base_units, display_units);
    } else {
	result = 0;
    }
    Py_XDECREF(val);
    Py_XDECREF(left);
    Py_XDECREF(right);
    Py_XDECREF(base_units);
    Py_XDECREF(display_units);
    return (PyObject *) result;
}

static 
PyObject *
value_div(PyObject *a, PyObject *b)
{
    WithUnitObject *left, *right, *result=0;
    PyObject *val;
    factor_t result_factor;
    UnitArray *base_units, *display_units;

    left = value_wrap(a);
    right = value_wrap(b);
    if (!left || !right) {
	Py_XDECREF(left);
	Py_XDECREF(right);
	PyErr_Clear();
	Py_INCREF(Py_NotImplemented);
	return Py_NotImplemented;
    }
    result_factor = factor_ratio(left->unit_factor, right->unit_factor);

    val = PyNumber_Divide(left->value, right->value);

    base_units = (UnitArray *)PyNumber_Divide((PyObject *)left->base_units, (PyObject *)right->base_units);
    display_units = (UnitArray *)PyNumber_Divide((PyObject *)left->display_units, (PyObject *)right->display_units);

    if(val && base_units && display_units)
	result = value_create(val, result_factor, base_units, display_units);

    Py_XDECREF(left);
    Py_XDECREF(right);
    Py_XDECREF(val);
    Py_XDECREF(base_units);
    Py_XDECREF(display_units);

    return (PyObject *) result;
}

static
PyObject *
value_divmod(PyObject *a, PyObject *b)
{
    WithUnitObject *left=0, *right=0;
    PyObject *scaled_left=0;
    PyObject *divmod_result=0;
    WithUnitObject *remainder=0;
    PyObject *factor_obj=0;
    double factor;

    left = value_wrap(a);
    right = value_wrap(b);
    if(!left || !right) {
	Py_XDECREF(left);
	Py_XDECREF(right);
	Py_INCREF(Py_NotImplemented);
	PyErr_Clear();
	return Py_NotImplemented;
    }
    if(!PyObject_RichCompareBool((PyObject *)left->base_units, (PyObject *)right->base_units, Py_EQ)) {
	PyErr_SetString(UnitMismatchError, "WithUnit __divmod__ requires equivalent units");
	goto fail;
    }
    
    factor = factor_ratio_double(left->unit_factor, right->unit_factor);
    factor_obj = PyFloat_FromDouble(factor);
    if(!factor_obj) goto fail;
    scaled_left = PyNumber_Multiply((PyObject *)left->value, factor_obj);
    if (!scaled_left) goto fail;
    divmod_result = PyNumber_Divmod(scaled_left, right->value);
    if (!divmod_result) goto fail;
    remainder = value_create(PyTuple_GetItem(divmod_result, 1), right->unit_factor, right->base_units, right->display_units);
    if(!remainder) goto fail;
    
    PyTuple_SetItem(divmod_result, 1, (PyObject *)remainder); 

    Py_DECREF(factor_obj);
    Py_DECREF(scaled_left);
    Py_DECREF(left);
    Py_DECREF(right);
    return divmod_result;
 fail: 
    Py_XDECREF(factor_obj);
    Py_XDECREF(scaled_left);
    Py_DECREF(left);
    Py_XDECREF(right);
    Py_XDECREF(divmod_result);
    return 0;
}

static
PyObject *
value_floordiv(PyObject *a, PyObject *b)
{
    PyObject *divmod_result, *result;
    divmod_result = value_divmod(a, b);
    if (!divmod_result)
	return 0;
    result = PyTuple_GetItem(divmod_result, 0);
    Py_INCREF(result);
    Py_DECREF(divmod_result);
    return result;
}

static
PyObject *
value_mod(PyObject *a, PyObject *b)
{
    PyObject *divmod_result, *result;
    divmod_result = value_divmod(a, b);
    if (!divmod_result)
	return 0;
    result = PyTuple_GetItem(divmod_result, 1);
    Py_INCREF(result);
    Py_DECREF(divmod_result);
    return result;

}
/*
 * Helper functions for calculating rational powers.
 */
static
long long ipow(long long x, int y)
{
    double tmp;

    tmp = pow(x, y);
    return (long long) tmp;
}

static
long long iroot(long long x, int y)
{
    long long tmp;
    tmp = pow(x, 1.0/y);
    if (pow(tmp, y) != x) {
	printf("%d root of %lld not an integer\n", y, x);
	return 0;
    }
    return tmp;
}

/* 
 * We allow calculating small rational powers, including the 2nd, 3rd,
 * and 4th roots.  This works even if you use a floating point exponent,
 * as long as it is "close enough".
 */

static
PyObject *
value_pow(PyObject *a, PyObject *b, PyObject *c)
{
    WithUnitObject *left, *result;
    factor_t result_factor;
    long pow_numer, pow_denom;
    PyObject *val;
    UnitArray *base_units, *display_units;

    if (c != Py_None) {
	PyErr_SetString(PyExc_ValueError, "WithUnit power does not support third argument");
	return 0;
    }
    if (!PyObject_IsInstance(a, (PyObject *)&WithUnitType)) {
	PyErr_SetString(PyExc_TypeError, "Can only raise value type to integer power");
	return 0;
    }
    left = (WithUnitObject *)a;
    if (!rational_power(b, &pow_numer, &pow_denom))
	return 0;

    if(!factor_pow(left->unit_factor, pow_numer, pow_denom, &result_factor))
	return 0;

    val = PyNumber_Power(left->value, b, Py_None);
    base_units = unit_array_pow_frac(left->base_units, pow_numer, pow_denom);
    display_units = unit_array_pow_frac(left->display_units, pow_numer, pow_denom);

    if (val && base_units && display_units)
	result = value_create(val, result_factor, base_units, display_units);
    else
	result = 0;
    Py_XDECREF(val);
    Py_XDECREF(base_units);
    Py_XDECREF(display_units);
    return (PyObject *)result;
}

static PyObject *
value_int(PyObject *obj)
{
    PyObject *f, *i;
    f = PyNumber_Float(obj);
    if (!f)
	return 0;
    i = PyNumber_Int(f);
    Py_DECREF(f);
    return i;
}

static PyObject *
value_long(PyObject *obj)
{
    PyObject *f, *l;
    f = PyNumber_Float(obj);
    if (!f)
	return 0;
    l = PyNumber_Int(f);
    Py_DECREF(f);
    return l;
}

static PyObject *
value_float(PyObject *obj)
{
    WithUnitObject *self = (WithUnitObject *)obj;
    if(self->base_units->ob_size != 0) {
	PyErr_SetString(PyExc_TypeError, "Can only convert dimensionless to float");
	return 0;
    }
    return PyNumber_Float(self->value);
}

static PyObject *
value_complex(WithUnitObject *self, PyObject *ignore)
{
    Py_complex c;
    if(self->base_units->ob_size != 0) {
	PyErr_SetString(UnitMismatchError, "Can only convert dimensionless to complex");
	return 0;
    }
    c = PyComplex_AsCComplex(self->value);
    if (c.real == -1 && PyErr_Occurred())
	return 0;
    return PyComplex_FromCComplex(c);
}

static PyObject *
value_array(WithUnitObject *self, PyObject *ignore)
{
    if(self->base_units->ob_size != 0) {
	PyErr_SetString(UnitMismatchError, "Can only convert dimensionless to plain ndarray");
	return 0;
    }
    Py_INCREF((PyObject *)self->value);
    return PyArray_EnsureArray(self->value);
}

static PyObject *
value_reduce(WithUnitObject *self, PyObject *ignore)
{
    PyObject *unitstr, *rv;

    unitstr = unit_array_str(self->display_units);
    rv = Py_BuildValue("O(ON)", &WithUnitType, self->value, unitstr);
    return rv;

}
static PyNumberMethods WithUnitNumberMethods = {
    value_add,			/* nb_add */
    value_sub,			/* nb_subtract */
    value_mul,			/* nb_multiply */
    value_div,			/* nb_divide */
    value_mod,		       	/* nb_remainder */
    value_divmod,	       	/* nb_divmod */
    value_pow,			/* nb_power */
    (unaryfunc)value_neg,     	/* nb_negative */
    value_pos,			/* nb_positive */
    (unaryfunc)value_abs,      	/* nb_absolute */
    (inquiry)value_nz,	       	/* nb_nonzero (Used by PyObject_IsTrue) */
    0,0,0,0,0,0,       		/* nb_* bitwise */
    0,				/* nb_coerce */
    value_int,                  /* nb_int */
    value_long,			/* nb_long coercions */
    value_float,		/* nb_float */
    0,0,			/* nb_* oct and hex conversions */
    0,0,0,0,0,0,0,0,0,0,0,	/* nb_inplace_* */
    value_floordiv,		/* nb_floor_divide */
    value_div,	       		/* nb_true_divide */
    0, 0			/* nb_inplace_*_divide */
};

static
PyObject *
value_richcompare(PyObject *a, PyObject *b, int op)
{
    WithUnitObject *left, *right;
    PyObject *new_left, *new_right, *ratio_obj;
    double ratio, factor_l, factor_r;
    PyObject *rv;

    left = value_wrap(a);
    right = value_wrap(b);

     if (!left || !right) {
	 Py_XDECREF(left);
	 Py_XDECREF(right);
	 Py_INCREF(Py_NotImplemented);
	 PyErr_Clear();
	 return Py_NotImplemented;
     }
     if(!PyObject_RichCompareBool((PyObject *)left->base_units, (PyObject *)right->base_units, Py_EQ)) {
	 Py_DECREF(left);
	 Py_DECREF(right);
	 if (op == Py_EQ)
	     Py_RETURN_FALSE;
	 if (op == Py_NE)
	     Py_RETURN_TRUE;
	 PyErr_SetString(UnitMismatchError, "UnitArray comparison requires equivalent units");
	 return 0;
     }
     factor_l = factor_to_double(left->unit_factor);
     factor_r = factor_to_double(right->unit_factor);
     if (factor_l < factor_r) {
	 ratio = factor_ratio_double(right->unit_factor, left->unit_factor);
	 ratio_obj = PyFloat_FromDouble(ratio);
	 new_right = PyNumber_Multiply((PyObject *)right->value, ratio_obj);
	 new_left = left->value;
	 Py_XDECREF(ratio_obj);
	 Py_INCREF(new_left);
     } else {
	 ratio = factor_ratio_double(left->unit_factor, right->unit_factor);
	 ratio_obj = PyFloat_FromDouble(ratio);
	 new_left = PyNumber_Multiply((PyObject *)left->value, ratio_obj);
	 new_right = right->value;
	 Py_XDECREF(ratio_obj);
	 Py_INCREF(new_right);
     }
     
     Py_DECREF(left);
     Py_DECREF(right);

     rv = PyObject_RichCompare(new_left, new_right, op);
     return rv;
}

static
PyObject *
value_str(WithUnitObject *obj)
{
    PyObject *result;
    PyObject *unit_repr_s;
    PyObject *value_repr_s;

    value_repr_s = PyObject_Str(obj->value);
    unit_repr_s = unit_array_str(obj->display_units);
    if(!unit_repr_s || !value_repr_s) {
	Py_XDECREF(unit_repr_s);
	Py_XDECREF(value_repr_s);
	return 0;
    }
    result = PyString_FromFormat("%s %s", PyString_AsString(value_repr_s), PyString_AsString(unit_repr_s));
    Py_XDECREF(value_repr_s);
    Py_XDECREF(unit_repr_s);
    return result;
}

static PyObject *
value_repr(WithUnitObject *obj)
{
    PyObject *result;
    PyObject *unit_repr_s;
    PyObject *value_repr_s;
    const char *name_ptr=0;

    value_repr_s = PyObject_Str(obj->value);
    unit_repr_s = unit_array_str(obj->display_units);
    if(!unit_repr_s || !value_repr_s) {
	Py_XDECREF(unit_repr_s);
	Py_XDECREF(value_repr_s);
	return 0;
    }
    name_ptr = strrchr(obj->ob_type->tp_name, '.');
    if(!name_ptr)
	name_ptr = obj->ob_type->tp_name;
    else
	name_ptr ++;
    result = PyString_FromFormat("%s(%s, \"%s\")", name_ptr, PyString_AsString(value_repr_s), PyString_AsString(unit_repr_s));
    Py_DECREF(value_repr_s);
    Py_DECREF(unit_repr_s);
    return result;
}

static WithUnitObject *
value_copy(WithUnitObject *self, PyObject *ignore)
{
	Py_INCREF(self);
	return self;
}

static WithUnitObject *
value_in_base_units(WithUnitObject *self, PyObject *ignore)
{
    PyObject *new_value;
    double factor;
    factor_t unit_factor = {{1},1, 0};
    PyObject *factor_obj;
    WithUnitObject *result;

    factor = factor_to_double(self->unit_factor);
    factor_obj = PyFloat_FromDouble(factor);
    if (!factor_obj) 
	return 0;

    new_value = PyNumber_Multiply(self->value, factor_obj);
    Py_DECREF(factor_obj);
    if (!new_value)
	return 0;

    result = value_create(new_value, unit_factor, self->base_units, self->base_units);
    Py_DECREF(new_value);
    return result;
}

static PyObject *
value_is_dimensionless(WithUnitObject *self, PyObject *ignore)
{
    if(self->base_units->ob_size == 0)
	Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *
value_numer(WithUnitObject *self, void *ignore)
{
    if(self->unit_factor.denom)
	return PyLong_FromLongLong(self->unit_factor.numer);
    else
	return PyFloat_FromDouble(self->unit_factor.ratio);
}

static PyObject *
valuearray_ndim(WithUnitObject *self, void *ignore)
{
    int ndim = PyArray_NDIM((PyArrayObject *)self->value);
    return PyInt_FromLong(ndim);
}

static PyObject *
valuearray_shape(WithUnitObject *self, void *ignore)
{
    int i;
    int ndim = PyArray_NDIM((PyArrayObject *)self->value);
    npy_intp *dims = PyArray_DIMS((PyArrayObject *)self->value);
    PyObject *result;

    result = PyTuple_New(ndim);
    if (!result)
	return 0;
    for(i=0; i<ndim; i++)
	PyTuple_SetItem(result, i, PyInt_FromLong(dims[i]));
    return result;
}

static PyObject *
valuearray_dtype(WithUnitObject *self, void *ignore)
{
    PyObject *result;
    result = (PyObject *)PyArray_DTYPE((PyArrayObject *)self->value);

    Py_XINCREF(result);
    return result;
}

static PyObject *
valuearray_size(WithUnitObject *self, void *ignore)
{
    npy_intp result;
    result = PyArray_SIZE((PyArrayObject *)self->value);

    return PyInt_FromLong(result);
}

static PyObject *
valuearray_dot(WithUnitObject *self, PyObject *b)
{
    factor_t result_factor;
    UnitArray *base_units=0, *display_units=0;
    PyObject *result_value=0, *result=0;
    
    WithUnitObject *other = value_wrap(b);
    if(!other)
	return 0;
    result_value = PyObject_CallMethod(self->value, "dot", "O", other->value);
    result_factor = factor_mul(self->unit_factor, other->unit_factor);
    base_units = (UnitArray *)PyNumber_Multiply((PyObject *)self->base_units, (PyObject *)other->base_units);
    display_units = (UnitArray *)PyNumber_Multiply((PyObject *)self->display_units, (PyObject *)other->display_units);

    if(result_value && base_units && display_units) 
	result = (PyObject *)value_create(result_value, result_factor, base_units, display_units);
    Py_XDECREF(base_units);
    Py_XDECREF(display_units);
    Py_XDECREF(result_value);
    return result;
}
/* __getitem__ is unfortunately overloaded for ValueArrays, so we have
 * to detect whether key is a unit or an index / slice object.  */

static PyObject *
value_getitem(PyObject *obj, PyObject *key)
{
    WithUnitObject *self = (WithUnitObject *)obj;
    WithUnitObject *unit_val=0;
    PyObject *result=0;
    PyObject *factor_obj=0;
    PyObject *new_val;
    double factor;

    unit_val = lookup_unit_val(key);
    if(unit_val) {
	if(!PyObject_RichCompareBool((PyObject *)self->base_units, (PyObject *)unit_val->base_units, Py_EQ)) {
	    PyErr_SetString(UnitMismatchError, "WithUnit __getitem__ requires equivalent units");
	    return 0;
	}
	factor = factor_ratio_double(self->unit_factor, unit_val->unit_factor);
	Py_XDECREF(unit_val);
	factor_obj = PyFloat_FromDouble(factor);
	if(factor_obj)
	    result = PyNumber_Multiply(factor_obj, self->value);
	Py_XDECREF(factor_obj);
	return result;
    }
    /* key wasn't a unit, try array slicing */
    PyErr_Clear();
    new_val = PyObject_GetItem(self->value, key);
    if (!new_val)
	return 0;
    result = (PyObject *)value_create(new_val, self->unit_factor, self->base_units, self->display_units);
    Py_XDECREF(new_val);
    return result;
}

/* These methods are needed to support the sequence protocol so we can iterate. 
 * They are only defined for ValueArrays not regular Value / Complex objects. 
 */

static Py_ssize_t
value_array_len(WithUnitObject *self)
{
    return PySequence_Size(self->value);
}

static PyObject *
value_array_get(WithUnitObject *self, Py_ssize_t i)
{
    PyObject *item=0;
    item = PySequence_GetItem(self->value, i);
    if(!item)
	return 0;
    return (PyObject *)value_create(item, self->unit_factor, self->base_units, self->display_units);
}

static PyObject *
value_in_units_of(PyObject *self, PyObject *unit)
{
    PyObject *new_val=0, *result=0;
    WithUnitObject *unit_val=0;
    
    unit_val = lookup_unit_val(unit);
    if(!unit_val)
	return 0;
    new_val = value_getitem(self, unit);
    if (!new_val) {
	Py_DECREF(unit_val);
	return 0;
    }
    result = (PyObject *)value_create(new_val, unit_val->unit_factor, unit_val->base_units, unit_val->display_units);
    Py_XDECREF(unit_val);
    Py_XDECREF(new_val);
    return result;
}

static PyObject *
value_is_compatible(WithUnitObject *self, PyObject *unit)
{
    WithUnitObject *unit_val=0;
    int rv;
    
    unit_val = lookup_unit_val(unit);
    if(!unit_val)
	return 0;
    rv = PyObject_RichCompareBool((PyObject *)self->base_units, (PyObject *)unit_val->base_units, Py_EQ);
    Py_XDECREF(unit_val);
    if (rv)
	Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

/*
 * Python hash functions need to always return the same value for any
 * two objects that compare equal.  In our case, this means that
 * hash(1000*m) and hash(1*km) must return the same result.
 * Therefore, we convert to base units before hashing.  The hash code
 * does not depend on the actual units, so hash(1*m) and hash(1*s) are
 * the same result, which is not a problem.  Finally, this makes sure
 * that hash(1) and hash(Value(1, '')) are the same.
 */
static long
value_hash(WithUnitObject *self)
{
    WithUnitObject *in_base=0;
    long result;

    in_base = value_in_base_units(self, 0);
    if (!in_base)
	return 0;

    result = PyObject_Hash(in_base->value);
    Py_DECREF(in_base);
    return result;
}

static int
value_setitem(WithUnitObject *self, PyObject *key, PyObject *val)
{
    double factor_l, factor_r;
    WithUnitObject *right=0;
    PyObject *bare_val=0;
    PyObject *factor_num=0;
    int result=0;
    
    right = value_wrap(val);
    if (!right)
	goto fail;
    
    if(!PyObject_RichCompareBool((PyObject *)self->base_units, (PyObject *)right->base_units, Py_EQ)) {
	PyErr_SetString(UnitMismatchError, "WithUnit __setitem__ requires equivalent units");
	goto fail;
    }
    factor_l = factor_to_double(self->unit_factor);
    factor_r = factor_to_double(right->unit_factor);
    factor_num = PyFloat_FromDouble(factor_r/factor_l);
    if (!factor_num) goto fail;

    bare_val = PyNumber_Multiply(right->value, factor_num);
    if (!bare_val) goto fail;
    result = PyObject_SetItem(self->value, key, bare_val);
 fail:
    Py_XDECREF(right);
    Py_XDECREF(factor_num);
    Py_XDECREF(bare_val);
    return result;
}

static PyObject *
value_set_py_func(PyTypeObject *t, PyObject *args)
{
    int rv;
    PyObject *f1, *f2, *o3, *f4;

    rv = PyArg_ParseTuple(args, "OOOO", &f1, &f2, &o3, &f4);
    if(!rv)
	return 0;
    
    PyDict_SetItemString(t->tp_dict, "unit", f1);
    PyModule_AddObject(module, "_unit_from_str", f2);
    unit_cache = o3;
    PyDict_SetItemString(t->tp_dict, "allclose", f4);
    Py_INCREF(unit_cache);

    Py_RETURN_NONE;
}

/* Value Array methods with 1 array argument:
 * 
 * T, conj, real, imag,									properties, call and add units
 * cumprod,cumsum,compress,diagonal,flatten,max,mean,min,prod,sum,trace,transpose	call and add units
 * all,argmax,argmin,argpartition,argsort,nonzero					call and return
 * astype,base,byteswap,byteswap,flags,round,floor,ceil					do not implement
 * clip,fill,flat,var,dot		Special case
 */

#define VALUE_ARRAY_METHOD_UNIT_RESULT(meth) static PyObject * value_array_ ## meth (WithUnitObject *self, PyObject *args, PyObject *kw) \
                                                 { \
						     PyObject *meth = PyObject_GetAttrString(self->value, #meth); \
						     PyObject *tmp=0;\
						     if (meth) \
							 tmp = PyObject_Call(meth, args, kw); \
						     Py_XDECREF(meth);\
						     if (!tmp)\
							 return 0;\
						     return (PyObject *)value_create(tmp, self->unit_factor, self->base_units, self->display_units);\
						 }

VALUE_ARRAY_METHOD_UNIT_RESULT(transpose);
VALUE_ARRAY_METHOD_UNIT_RESULT(cumprod);
VALUE_ARRAY_METHOD_UNIT_RESULT(cumsum);
VALUE_ARRAY_METHOD_UNIT_RESULT(compress);
VALUE_ARRAY_METHOD_UNIT_RESULT(diagonal);
VALUE_ARRAY_METHOD_UNIT_RESULT(flatten);
VALUE_ARRAY_METHOD_UNIT_RESULT(max);
VALUE_ARRAY_METHOD_UNIT_RESULT(min);
VALUE_ARRAY_METHOD_UNIT_RESULT(mean);
VALUE_ARRAY_METHOD_UNIT_RESULT(std);
VALUE_ARRAY_METHOD_UNIT_RESULT(prod);
VALUE_ARRAY_METHOD_UNIT_RESULT(sum);
VALUE_ARRAY_METHOD_UNIT_RESULT(trace);
VALUE_ARRAY_METHOD_UNIT_RESULT(conj);
VALUE_ARRAY_METHOD_UNIT_RESULT(conjugate);
VALUE_ARRAY_METHOD_UNIT_RESULT(choose);
VALUE_ARRAY_METHOD_UNIT_RESULT(reshape);
VALUE_ARRAY_METHOD_UNIT_RESULT(resize);

#define VALUE_ARRAY_ATTR(attr) static PyObject * value_array_ ## attr (WithUnitObject *self, PyObject *ignore) \
                               {\
				   PyObject *tmp = PyObject_GetAttrString(self->value, #attr); \
				   if (!tmp)\
				       return 0;\
				   return (PyObject *)value_create(tmp, self->unit_factor, self->base_units, self->display_units);\
			       }
VALUE_ARRAY_ATTR(real)
VALUE_ARRAY_ATTR(imag)
VALUE_ARRAY_ATTR(T)


#define VALUE_ARRAY_METHOD(meth) static PyObject * value_array_ ## meth (WithUnitObject *self, PyObject *args, PyObject *kw) \
                                 { \
				     PyObject *meth = PyObject_GetAttrString(self->value, #meth);\
				     if (!meth)\
					 return 0;\
				     return PyObject_Call(meth, args, kw);	\
				 }

VALUE_ARRAY_METHOD(all)
VALUE_ARRAY_METHOD(any)
VALUE_ARRAY_METHOD(argmin)
VALUE_ARRAY_METHOD(argmax)
VALUE_ARRAY_METHOD(argpartition)
VALUE_ARRAY_METHOD(argsort)
VALUE_ARRAY_METHOD(nonzero) 

static PyMethodDef WithUnit_methods[] = {
    {"inBaseUnits", (PyCFunction)value_in_base_units, METH_NOARGS, "@returns: the same quantity converted to base units,  i.e. SI units in most cases"},
    {"isDimensionless", (PyCFunction)value_is_dimensionless, METH_NOARGS, "returns true if the value is dimensionless"},
    {"inUnitsOf", (PyCFunction)value_in_units_of, METH_O, "Convert to the specified units"},
    {"isCompatible", (PyCFunction)value_is_compatible, METH_O, "Check if the value is compatible with the specified unit"},
    {"isCompatible", (PyCFunction)value_is_compatible, METH_O, "Check if the value is compatible with the specified unit"},
    {"_new_raw", (PyCFunction)value_new_raw, METH_VARARGS | METH_KEYWORDS | METH_CLASS, "Create value unit from factor and UnitArray objects"},
    {"_set_py_func", (PyCFunction)value_set_py_func, METH_VARARGS | METH_CLASS, "Internal method: setup proxy object for python calls"},
    {"__copy__", (PyCFunction)value_copy, METH_NOARGS, "Copy function"},
    {"__deepcopy__", (PyCFunction)value_copy, METH_VARARGS, "Copy function"},
    {"__complex__", (PyCFunction)value_complex, METH_NOARGS, "@returns: quantity converted to a bare complex number"},
    {"__array__", (PyCFunction)value_array, METH_VARARGS, "@returns: quantity converted to a numpy array"},
    {"__reduce__", (PyCFunction)value_reduce, METH_NOARGS, "@returns: tuple used by pickling protocol"},
    {0}
};

static PyMemberDef WithUnit_members[] = {
    {"_value", T_OBJECT_EX, offsetof(WithUnitObject, value), READONLY, "Floating point value"},
    {"base_units", T_OBJECT_EX, offsetof(WithUnitObject, base_units), READONLY, "Units in base units"},
    {"display_units", T_OBJECT_EX, offsetof(WithUnitObject, display_units), READONLY, "Units for display"},
    {"denom", T_LONGLONG, offsetof(WithUnitObject, unit_factor.denom), READONLY, "Denominator of ratio between base and display units (0 means numer is float)"},
    {"_numer_int", T_LONGLONG, offsetof(WithUnitObject, unit_factor.numer), READONLY, "Integer representation of numerator (denom!=0)"},
    {"_numer_double", T_DOUBLE, offsetof(WithUnitObject, unit_factor.ratio), READONLY, "Double representation of numerator (denom==0)"},
    {"exp10", T_INT, offsetof(WithUnitObject, unit_factor.exp_10), READONLY, "Power of 10 of ratio between base and display units"},
    {NULL}};

static PyGetSetDef WithUnit_getset[] = {
    {"numer", (getter)value_numer, NULL, "Numerator part of ratio between base and display units (int or float)", 0}, 
    {NULL}};

#define VALUE_ARRAY_METHODDEF(meth) {#meth, (PyCFunction)value_array_ ## meth, METH_VARARGS | METH_KEYWORDS, "See numpy function numpy." #meth " for details"}

static PyMethodDef ValueArray_methods[] = {
    VALUE_ARRAY_METHODDEF(transpose),
    VALUE_ARRAY_METHODDEF(cumprod),
    VALUE_ARRAY_METHODDEF(cumsum),
    VALUE_ARRAY_METHODDEF(compress),
    VALUE_ARRAY_METHODDEF(diagonal),
    VALUE_ARRAY_METHODDEF(flatten),
    VALUE_ARRAY_METHODDEF(max),
    VALUE_ARRAY_METHODDEF(min),
    VALUE_ARRAY_METHODDEF(mean),
    VALUE_ARRAY_METHODDEF(std),
    VALUE_ARRAY_METHODDEF(prod),
    VALUE_ARRAY_METHODDEF(sum),
    VALUE_ARRAY_METHODDEF(trace),
    VALUE_ARRAY_METHODDEF(all),
    VALUE_ARRAY_METHODDEF(any),
    VALUE_ARRAY_METHODDEF(argmin),
    VALUE_ARRAY_METHODDEF(argmax),
    VALUE_ARRAY_METHODDEF(argpartition),
    VALUE_ARRAY_METHODDEF(argsort),
    VALUE_ARRAY_METHODDEF(nonzero),
    VALUE_ARRAY_METHODDEF(conj),
    VALUE_ARRAY_METHODDEF(conjugate),
    VALUE_ARRAY_METHODDEF(choose),
    VALUE_ARRAY_METHODDEF(reshape),
    VALUE_ARRAY_METHODDEF(resize),
    {"dot", (PyCFunction)valuearray_dot, METH_O, "Array dot product / matrix product"},
    {0}
};
    
static PyGetSetDef ValueArray_getset[] = {
    {"dtype", (getter)valuearray_dtype, NULL, "dtype of underlying numpy array", 0},
    {"ndim", (getter)valuearray_ndim, NULL, "number of dimensions", 0},
    {"shape", (getter)valuearray_shape, NULL, "Shape of underlying numpy array", 0},
    {"size", (getter)valuearray_size, NULL, "Overall size of array", 0},
    {"real", (getter)value_array_real, NULL, "Real part", 0},
    {"imag", (getter)value_array_imag, NULL, "Imaginary part", 0},
    {"T", (getter)value_array_T, NULL, "Transpose", 0},
    {NULL}};


static PyMappingMethods WithUnitMappingMethods = {
    0,			/* mp_length */
    (binaryfunc)value_getitem,	/* mp_subscript */
    (objobjargproc)value_setitem,     	/* mp_ass_subscript */
};

static PySequenceMethods ValueArraySequenceMethods = {
    (lenfunc)value_array_len,        /* sq_length */
    0,                               /* sq_concat */
    0,                               /* sq_len */
    (ssizeargfunc)value_array_get,   /* sq_item */
    0                                /* ... */
};

static PyTypeObject WithUnitType = {
    PyObject_HEAD_INIT(NULL) 
    0,			       /* ob_size */
    "fastunits.WithUnit",		       /* tp_name */
    sizeof(WithUnitObject),    /* tp_basicsize */
    0,                         /* tp_itemsize */
    (destructor)value_dealloc, /* tp_dealloc */
    0,                         /* tp_print */
    0,                         /* tp_getattr */
    0,                         /* tp_setattr */
    0,                         /* tp_compare */
    (reprfunc)value_repr,      /* tp_repr */
    &WithUnitNumberMethods,    /* tp_as_number */
    0,                         /* tp_as_sequence */
    &WithUnitMappingMethods,   /* tp_as_mapping */
    (hashfunc)value_hash,      /* tp_hash */
    0,                         /* tp_call */
    (reprfunc)value_str,       /* tp_str */
    0,                         /* tp_getattro */
    0,                         /* tp_setattro */
    0,                         /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT|Py_TPFLAGS_CHECKTYPES,        /*tp_flags*/
    "Unit Array object",       /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    value_richcompare,	       /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    WithUnit_methods,          /* tp_methods */
    WithUnit_members,	       /* tp_members */
    WithUnit_getset,           /* tp_getset */
    0,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,                         /* tp_init */
    0,                         /* tp_alloc */
    value_new,                 /* tp_new */
    0
};

static PyTypeObject ValueType = {
    PyObject_HEAD_INIT(NULL) 
    0,			      /* ob_size */
    "fastunits.Value",		      /* tp_name */
    sizeof(WithUnitObject),   /* tp_basicsize*/
    0                         /* tp_itemsize*/
};

static PyTypeObject ComplexType = {
    PyObject_HEAD_INIT(NULL) 
    0,			      /* ob_size */
    "fastunits.Complex",		      /* tp_name */
    sizeof(WithUnitObject),   /* tp_basicsize*/
    0                         /* tp_itemsize*/
};

static PyTypeObject ValueArrayType = {
    PyObject_HEAD_INIT(NULL) 
    0,			          /* ob_size */
    "fastunits.ValueArray",		  /* tp_name */
    sizeof(WithUnitObject),       /* tp_basicsize*/
    0                             /* tp_itemsize*/
};


#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC
initunitarray(void) 
{
    if (PyType_Ready(&UnitArrayType) < 0)
	return;
    if (PyType_Ready(&WithUnitType) < 0)
	return;
    ValueType.tp_base = &WithUnitType;
    ValueType.tp_flags = Py_TPFLAGS_DEFAULT|Py_TPFLAGS_CHECKTYPES;
    ComplexType.tp_base = &WithUnitType;
    ComplexType.tp_flags = Py_TPFLAGS_DEFAULT|Py_TPFLAGS_CHECKTYPES;
    ValueArrayType.tp_base = &WithUnitType;
    ValueArrayType.tp_getset = ValueArray_getset;
    ValueArrayType.tp_methods = ValueArray_methods;
    ValueArrayType.tp_flags = Py_TPFLAGS_DEFAULT|Py_TPFLAGS_CHECKTYPES;
    ValueArrayType.tp_as_sequence = &ValueArraySequenceMethods;

    if (PyType_Ready(&ValueType) < 0)
	return;
    if (PyType_Ready(&ComplexType) < 0)
	return;
    if (PyType_Ready(&ValueArrayType) < 0)
	return;
    UnitMismatchError = PyErr_NewExceptionWithDoc("fastunits.unitarray.UnitMismatchError", "Raised when operations fail due to a unit mismatch.", PyExc_TypeError, 0);
    PyDict_SetItemString(WithUnitType.tp_dict, "__array_priority__", PyInt_FromLong(15));
    module = Py_InitModule3("unitarray", 0, "Module that creates unit arrays");
    Py_INCREF(&UnitArrayType);
    Py_INCREF(&WithUnitType);
    Py_INCREF(&ValueType);
    Py_INCREF(&ComplexType);
    Py_INCREF(&ValueArrayType);

    dimensionless = (UnitArray *)UnitArrayType.tp_alloc(&UnitArrayType, 0);
    dimensionless->ob_size = 0;
    import_array()
    PyModule_AddObject(module, "UnitArray", (PyObject *)&UnitArrayType);
    PyModule_AddObject(module, "WithUnit", (PyObject *)&WithUnitType);
    PyModule_AddObject(module, "Value", (PyObject *)&ValueType);
    PyModule_AddObject(module, "Complex", (PyObject *)&ComplexType);
    PyModule_AddObject(module, "ValueArray", (PyObject *)&ValueArrayType);
    PyModule_AddObject(module, "DimensionlessUnit", (PyObject *)dimensionless);
    PyModule_AddObject(module, "UnitMismatchError", (PyObject *)UnitMismatchError);
}
