from __future__ import with_statement
import os
import re

from parse import (LibrarySource, Constant, Parameter,
        Subroutine, Type, DoxygenGrouping)


def generate(cm_path, args):
    opencmiss_h_path, opencmiss_iron_c_f90_path = args

    library = LibrarySource(cm_path)

    with open(opencmiss_h_path, 'w') as opencmissh:
        write_c_header(library, opencmissh)
    with open(opencmiss_iron_c_f90_path, 'w') as opencmissironcf90:
        write_c_f90(library, opencmissironcf90)


def _logical_type():
    """Return the C type to match Fortran the logical type

    This may depend on the compiler used
    """

    # Both ifortran and gfortran use 4 bytes
    # uint32_t is optional so might not be defined
    return "unsigned int"


C_DEFINES = ('\n/*\n * Defines\n */\n\n'
        'const int CMFE_NO_ERROR = 0;\n'
        'const int CMFE_POINTER_IS_NULL = -1;\n'
        'const int CMFE_POINTER_NOT_NULL = -2;\n'
        'const int CMFE_COULD_NOT_ALLOCATE_POINTER = -3;\n'
        'const int CMFE_ERROR_CONVERTING_POINTER = -4;\n\n'
        'typedef %s cmfe_Bool;\n'
        'const cmfe_Bool cmfe_True = 1;\n'
        'const cmfe_Bool cmfe_False = 0;\n\n'
        'typedef int cmfe_Error;\n\n' % _logical_type())


def write_c_header(library, output):
    """Write C header with constants, typedefs and routine declarations

    Arguments:
    output -- File to write to
    """

    output.write('/*\n * opencmiss.h. This file is automatically generated '
        'from opencmiss.f90 and opencmiss_iron.f90.\n'
        ' * Do not edit this file directly, instead edit opencmiss.f90, opencmiss_iron.f90 or the '
        'generate_bindings script\n */\n\n'
        '#ifndef OPENCMISS_H\n'
        '#define OPENCMISS_H\n')

    output.write(C_DEFINES)

    for o in library.ordered_objects:
        if isinstance(o, Subroutine):
            output.write(subroutine_to_c_header(o))
        elif isinstance(o, Constant):
            output.write(constant_to_c_header(o))
        elif isinstance(o, Type):
            output.write(type_to_c_header(o))
        elif isinstance(o, DoxygenGrouping):
            output.write(doxygen_to_c_header(o))

    output.write('\n#endif\n')


def write_c_f90(library, output):
    """Write iron_c.f90 containing Fortran routines

    Arguments:
    output -- File to write to
    """


    output.write('!\n! iron_c.f90. This file is automatically generated '
        'from opencmiss_iron.f90.\n'
        '! Do not edit this file directly, instead edit opencmiss_iron.f90 or the '
        'generate_bindings script\n!\n'
        '#include "dllexport.h"\n'
        'MODULE OpenCMISS_Iron_C\n\n'
        '  USE ISO_C_BINDING\n'
        '  USE ISO_VARYING_STRING\n'
        '  USE OpenCMISS_Iron\n'
        '  USE CMISS_FORTRAN_C\n\n'
        '  IMPLICIT NONE\n\n'
        '  PRIVATE\n\n'
        '  INTEGER(C_INT), PARAMETER :: cmfe_True = 1\n'
        '  INTEGER(C_INT), PARAMETER :: cmfe_False = 0\n'
        '  INTEGER(C_INT), PARAMETER :: CMFE_NO_ERROR = 0\n'
        '  INTEGER(C_INT), PARAMETER :: CMFE_POINTER_IS_NULL = -1\n'
        '  INTEGER(C_INT), PARAMETER :: CMFE_POINTER_NOT_NULL = -2\n'
        '  INTEGER(C_INT), PARAMETER :: CMFE_COULD_NOT_ALLOCATE_POINTER = -3\n'
        '  INTEGER(C_INT), PARAMETER :: CMFE_ERROR_CONVERTING_POINTER = -4\n\n')

    output.write('\n'.join(('  PUBLIC %s' % subroutine_c_names(subroutine)[1]
            for subroutine in library.public_subroutines)))
    output.write('\nCONTAINS\n\n')

    for subroutine in library.public_subroutines:
        output.write(subroutine_to_c_f90(subroutine))

    output.write('END MODULE OpenCMISS_Iron_C')


# Corresponding variable types for C
PARAMETER_CTYPES = {
    Parameter.INTEGER: 'int',
    Parameter.FLOAT: 'float',
    Parameter.DOUBLE: 'double',
    Parameter.CHARACTER: 'char',
    Parameter.LOGICAL: 'cmfe_Bool',
    Parameter.CUSTOM_TYPE: None}


# Variable types as used in opencmiss_iron_c.f90
PARAMETER_F90TYPES = {
    Parameter.INTEGER: 'INTEGER(C_INT)',
    Parameter.FLOAT: 'REAL(C_FLOAT)',
    Parameter.DOUBLE: 'REAL(C_DOUBLE)',
    Parameter.CHARACTER: 'CHARACTER(LEN=1,KIND=C_CHAR)',
    Parameter.LOGICAL: 'LOGICAL',
    Parameter.CUSTOM_TYPE: 'TYPE(C_PTR)'}


def constant_to_c_header(constant):
    """Return the C definition of this constant"""

    if constant.resolved:
        if constant.comment != '':
            return 'const int %s = %d; /*<%s */\n' % (constant.name,
                    constant.value, constant.comment)
        else:
            return 'const int %s = %d;\n' % (constant.name, constant.value)
    else:
        return ''


def subroutine_c_names(subroutine):
    """Get the name of the routine as used from C and in iron_c.f90

    Sets the subroutines c_name and c_f90_name parameters
    """

    # Note that some interfaces have a 'C' variant with C in the name already:
    if re.search(r'Obj[0-9]*C*$', subroutine.name):
        # For routines with a Region and Interface variant, the Region one
        # is default and Region is removed from the name
        c_name = re.sub(r'(Region)?C*(Obj)[0-9]*C*$', '', subroutine.name)
        c_f90_name = re.sub(r'(Region)?C*Obj[0-9]*C*$', 'C', subroutine.name)
    elif re.search(r'Number[0-9]*C*$', subroutine.name):
        c_name = re.sub(r'C*Number[0-9]*C?$', r'Num', subroutine.name)
        c_f90_name = re.sub(r'C*Number[0-9]*C*$', r'CNum', subroutine.name)
    else:
        c_name = re.sub(r'C*[0-9]*$', '', subroutine.name)
        c_f90_name = re.sub(r'C*[0-9]*$', r'C', subroutine.name)
    # Make sure names are different, might have matched a C at the end of
    # the subroutine name
    if c_f90_name == subroutine.name:
        c_f90_name = subroutine.name + 'C'
    return c_name, c_f90_name


def subroutine_to_c_header(subroutine):
    """Returns the function declaration in C"""

    output = ['\n/*>']
    output.append('\n *>'.join(subroutine.comment_lines))
    output.append(' */\n')
    output.append('cmfe_Error %s(' % subroutine_c_names(subroutine)[0])

    c_parameters = _chain_iterable([parameter_to_c(p)
            for p in subroutine.parameters])
    comments = _chain_iterable([parameter_doxygen_comments(p)
            for p in subroutine.parameters])
    output.append(',\n    '.join(['%s /*<%s */' % (p, c)
            for (p, c) in zip(c_parameters, comments)]))
    output.append(');\n')
    return ''.join(output)


def subroutine_to_c_f90(subroutine):
    """Returns the C function implemented in Fortran for opencmiss_iron_c.f90"""

    c_f90_params = [parameter_c_f90_names(param)
            for param in subroutine.parameters]
    c_f90_declarations = _chain_iterable([parameter_c_f90_declaration(param)
            for param in subroutine.parameters])
    if subroutine.interface is not None:
        function_call = subroutine.interface.name
    else:
        function_call = subroutine.name

    (c_name, c_f90_name) = subroutine_c_names(subroutine)
    
    output = []
    output.append('  FUNCTION %s(%s) &' % (c_f90_name, ','.join(c_f90_params)))
    output.append('    & BIND(C, NAME="%s")' % c_name)
    output.append('    !DLLEXPORT(%s)\n' % c_f90_name)
    output.append('    !Argument variables')
    output.extend(['    %s' % d for d in c_f90_declarations])
    output.append('    !Function return variable')
    output.append('    INTEGER(C_INT) :: %s' % c_f90_name)
    output.append('    !Local variables')

    pre_post_lines = [parameter_conversion(parameter)
            for parameter in subroutine.parameters]
    local_variables = list(_chain_iterable([p[0] for p in pre_post_lines]))
    pre_lines = list(_chain_iterable([p[1] for p in pre_post_lines]))
    post_lines = list(_chain_iterable(reversed([p[2]
            for p in pre_post_lines])))

    content = []
    content.extend(local_variables)
    content.append('')
    content.append('%s = CMFE_NO_ERROR' % c_f90_name)
    content.extend(pre_lines)
    content.append('CALL %s(%s)' % (function_call,
            ','.join([parameter_call_name(p) for p in subroutine.parameters] +
            [c_f90_name])))
    content.extend(post_lines)
    output.extend(_indent_lines(content, 2, 4))

    output.append('\n    RETURN\n')
    output.append('  END FUNCTION %s\n' % c_f90_name)
    output.append('  !')
    output.append('  !' + '=' * 129)
    output.append('  !\n\n')
    output = '\n'.join([_fix_length(line) for line in output])
    return output


def parameter_conversion(parameter):
    """Get any extra conversions or checks required in the Fortran wrapper

    Sets pre_call and post_call properties, which are lines to add before and
    after calling the routine in opencmiss_iron.f90
    """

    local_variables = []
    pre_call = []
    post_call = []

    (routine_c_name, routine_c_f90_name) = (
        subroutine_c_names(parameter.routine))

    c_f90_name = parameter_c_f90_name(parameter)
    size_list = parameter_size_list(parameter)[0]

    # CMFE Types
    if parameter.var_type == Parameter.CUSTOM_TYPE:
        if parameter.array_dims > 0:
            local_variables.append('TYPE(%s), TARGET :: %s(%s)' %
                    (parameter.type_name, parameter.name, ','.join(size_list)))
        else:
            local_variables.append('TYPE(%s), POINTER :: %s' %
                    (parameter.type_name, parameter.name))
        # If we're in a CMFE...TypeInitialise routine, then objects get
        # allocated in Fortran and we need to convert pointers to C pointers
        # before returning them.  For all other routines the pointer to the
        # buffer object doesn't change so we ignore the intent and always check
        # for association before calling the Fortran routine.
        if parameter.routine.name.endswith('_Initialise'):
            local_variables.append('INTEGER(C_INT) :: Err')
            pre_call.extend(('IF(C_ASSOCIATED(%sPtr)) THEN' % parameter.name,
                '%s = CMFE_POINTER_NOT_NULL' % routine_c_f90_name,
                'ELSE',
                'NULLIFY(%s)' % parameter.name,
                'ALLOCATE(%s, STAT = Err)' % parameter.name,
                'IF(Err /= 0) THEN',
                '%s = CMFE_COULD_NOT_ALLOCATE_POINTER' % routine_c_f90_name,
                'ELSE'))

            post_call.extend(('%sPtr=C_LOC(%s)' % (parameter.name,
                    parameter.name), 'ENDIF', 'ENDIF'))
        elif parameter.routine.name.endswith('_Finalise'):
            pre_call.extend(('IF(C_ASSOCIATED(%sPtr)) THEN' % parameter.name,
                'CALL C_F_POINTER(%(name)sPtr,%(name)s)' % parameter.__dict__,
                'IF(ASSOCIATED(%s)) THEN' % parameter.name))

            post_call.extend(('DEALLOCATE(%s)' % parameter.name,
                '%sPtr = C_NULL_PTR' % parameter.name,
                'ELSE',
                '%s = CMFE_ERROR_CONVERTING_POINTER' % routine_c_f90_name,
                'ENDIF',
                'ELSE',
                '%s = CMFE_POINTER_IS_NULL' % routine_c_f90_name,
                'ENDIF'))
        else:
            if parameter.array_dims > 0:
                pre_call.append('IF(C_ASSOCIATED(%sPtr)) THEN' %
                        parameter.name)
                if parameter.intent == 'IN':
                    # Passing an array of CMFE Types to Fortran
                    pre_call.append('CALL %ssCopy(%s,%sSize,%sPtr,%s)' %
                            (parameter.type_name, parameter.name,
                            parameter.name, parameter.name,
                            routine_c_f90_name))
                else:
                    # Getting an array of CMFE Types from Fortran and
                    # setting an array of C pointers
                    local_variables.append('INTEGER(C_INT) :: %sIndex' %
                        parameter.name)
                    local_variables.append('TYPE(C_PTR), POINTER :: %sCPtrs(:)'
                        % parameter.name)
                    post_call.extend(('CALL C_F_POINTER(%sPtr,%sCPtrs,[%s])' %
                        (parameter.name, parameter.name, ','.join(size_list)),
                        'DO %sIndex=1,%sSize' % (parameter.name,
                        parameter.name),
                        '%sCPtrs(%sIndex) = C_LOC(%s(%sIndex))' %
                        ((parameter.name,) * 4), 'ENDDO'))
                post_call.extend(('ELSE',
                    '%s = CMFE_POINTER_IS_NULL' % routine_c_f90_name,
                    'ENDIF'))
            else:
                pre_call.extend(('IF(C_ASSOCIATED(%s)) THEN' % c_f90_name,
                    'CALL C_F_POINTER(%(name)sPtr,%(name)s)' %
                    parameter.__dict__,
                    'IF(ASSOCIATED(%s)) THEN' % parameter.name))
                post_call.extend(('ELSE',
                    '%s = CMFE_ERROR_CONVERTING_POINTER' % routine_c_f90_name,
                    'ENDIF',
                    'ELSE',
                    '%s = CMFE_POINTER_IS_NULL' % routine_c_f90_name,
                    'ENDIF'))

    # Character arrays
    elif parameter.var_type == Parameter.CHARACTER:
        if parameter.array_dims > 1:
            # Fortran array has one less dimension
            char_sizes = '(%s)' % ','.join(size_list[:-1])
        else:
            char_sizes = ''
        local_variables.append('CHARACTER(LEN=%s-1) :: Fortran%s%s' %
            (size_list[-1], parameter.name, char_sizes))
        local_variables.append('%s, POINTER :: %sCChars(%s)' %
            (PARAMETER_F90TYPES[parameter.var_type], parameter.name,
            ','.join(':' * parameter.array_dims)))
        if parameter.intent == 'IN':
            # reverse to account for difference in storage order
            pre_call.append('CALL C_F_POINTER(%s,%sCChars,[%s])' %
                (parameter.name, parameter.name,
                ','.join(reversed(size_list))))
            if parameter.array_dims > 1:
                char_sizes = '(%s)' % ','.join(size_list[:-1])
                pre_call.append('CALL CMISSC2FStrings(%sCChars,Fortran%s)' %
                    (parameter.name, parameter.name))
            else:
                char_sizes = ''
                pre_call.append('CALL CMISSC2FString(%sCChars,Fortran%s)' %
                    (parameter.name, parameter.name))
        else:
            if parameter.array_dims > 1:
                raise ValueError("output of strings >1D not implemented")
            post_call.append('CALL C_F_POINTER(%s,%sCChars,[%s])' %
                (parameter.name, parameter.name, size_list[0]))
            post_call.append('CALL CMISSF2CString(Fortran%s,%sCChars)' %
                (parameter.name, parameter.name))

    # Arrays of floats, integers or logicals
    elif parameter.array_dims > 0:
        if parameter.var_type == Parameter.CHARACTER:
            local_variables.append('CHARACTER, POINTER :: %s(%s)' %
                (parameter.name, ','.join([':'] * parameter.array_dims)))
        else:
            local_variables.append('%s, POINTER :: %s(%s)' %
                (PARAMETER_F90TYPES[parameter.var_type], parameter.name,
                ','.join([':'] * parameter.array_dims)))
        if parameter.pointer == True and c_intent(parameter) == 'OUT':
            # we are setting the value of a pointer
            # Note: here and below only work for 1D arrays
            pre_call.append('NULLIFY(%s)' % parameter.name)
            post_call.extend(('%sPtr = C_LOC(%s(1))' % (parameter.name,
                parameter.name),
                '%sSize = SIZE(%s,1)' % (parameter.name, parameter.name),
                'IF(.NOT.C_ASSOCIATED(%sPtr)) THEN' % parameter.name,
                '%s = CMFE_ERROR_CONVERTING_POINTER' % routine_c_f90_name,
                'ENDIF'))
        elif parameter.pointer == True and c_intent(parameter) == 'INOUT':
            # we are getting the value from a pointer and then setting
            # it on return
            pre_call.extend(('IF(C_ASSOCIATED(%s)) THEN' % c_f90_name,
                'CALL C_F_POINTER(%s,%s,[%s])' % (c_f90_name, parameter.name,
                ','.join(size_list)),
                'IF(ASSOCIATED(%s)) THEN' % parameter.name))

            # On return, the Fortran pointer may or may not be associated
            post_call.extend((
                'IF(ASSOCIATED(%s)) THEN' % parameter.name,
                '%sPtr = C_LOC(%s(1))' % (parameter.name, parameter.name),
                '%sSize = SIZE(%s,1)' % (parameter.name, parameter.name),
                'IF(.NOT.C_ASSOCIATED(%sPtr)) THEN' % parameter.name,
                '%s = CMFE_ERROR_CONVERTING_POINTER' % routine_c_f90_name,
                'ENDIF',
                'ELSE',
                '%sPtr = C_NULL_PTR' % parameter.name,
                '%sSize = 0' % parameter.name,
                'ENDIF',
                ))
            post_call.extend(('ELSE',
                '%s = CMFE_ERROR_CONVERTING_POINTER' % routine_c_f90_name,
                'ENDIF',
                'ELSE',
                '%s = CMFE_POINTER_IS_NULL' % routine_c_f90_name,
                'ENDIF'))
        else:
            # pointer is pointing to allocated memory that is being set
            pre_call.extend(('IF(C_ASSOCIATED(%s)) THEN' % c_f90_name,
                'CALL C_F_POINTER(%s,%s,[%s])' % (c_f90_name, parameter.name,
                ','.join(size_list)),
                'IF(ASSOCIATED(%s)) THEN' % parameter.name))
            post_call.extend(('ELSE',
                '%s = CMFE_ERROR_CONVERTING_POINTER' % routine_c_f90_name,
                'ENDIF',
                'ELSE',
                '%s = CMFE_POINTER_IS_NULL' % routine_c_f90_name,
                'ENDIF'))

    return (local_variables, pre_call, post_call)


def parameter_c_f90_name(parameter):
    """Return the name of the parameter as used in opencmiss_iron_c.f90"""

    c_f90_name = parameter.name
    if (parameter.var_type == Parameter.CUSTOM_TYPE or
            (parameter.array_dims > 0 and parameter.var_type !=
            Parameter.CHARACTER)):
        c_f90_name += 'Ptr'
    return c_f90_name


def parameter_c_f90_names(parameter):
    """Return param name + name of size param if it exists,
    separated by a comma for use in the function declaration in Fortran
    """

    return ','.join([s for s in parameter_size_list(parameter)[1]] +
            [parameter_c_f90_name(parameter)])


def parameter_c_f90_declaration(parameter):
    """Return the parameter declaration for use in opencmiss_iron_c.f90

    Returns a list including any extra parameters required"""

    c_f90_name = parameter_c_f90_name(parameter)
    output = []

    param_cintent = c_intent(parameter)
    # pass by value?
    if param_cintent == 'IN':
        value = 'VALUE, '
    else:
        value = ''

    # possible size parameter
    if parameter.pointer == True and param_cintent != 'IN':
        size_type = 'INTEGER(C_INT), INTENT(%s)' % param_cintent
    else:
        size_type = 'INTEGER(C_INT), VALUE, INTENT(IN)'
    output.extend([size_type + ' :: ' + size_name
        for size_name in parameter_size_list(parameter)[1]])

    if parameter.array_dims > 0:
        output.append('TYPE(C_PTR), %sINTENT(%s) :: %s' %
                (value, param_cintent, c_f90_name))
    else:
        output.append('%s, %sINTENT(%s) :: %s' % (
                PARAMETER_F90TYPES[parameter.var_type], value,
                param_cintent, c_f90_name))
    return output


def parameter_call_name(parameter):
    """The parameter name used when calling the Fortran subroutine

    Used to pass the name of a converted variable
    """

    output = parameter.name
    if parameter.var_type == Parameter.CHARACTER:
        output = 'Fortran' + output
    return output


def parameter_to_c(parameter):
    """Calculate C parameter declaration for opencmiss.h

    Returns a list of parameters, including extra size parameters
    for arrays.
    """

    param = parameter.name
    # array or pointer argument?
    if (parameter.array_dims == 1 and parameter.required_sizes == 0):
        param = param + '[' + parameter.array_spec[0] + ']'
    elif (parameter.array_dims > 0 or parameter.var_type == Parameter.CHARACTER
            or c_intent(parameter) == 'OUT'):
        param = '*' + param
    if parameter.pointer == True:
        # add another * as we need a pointer to a pointer,
        # to modify the pointer value
        param = '*' + param

    # parameter type
    if parameter.var_type != Parameter.CUSTOM_TYPE:
        param = PARAMETER_CTYPES[parameter.var_type] + ' ' + param
    else:
        param = parameter.type_name + ' ' + param

    # const?
    if parameter.intent == 'IN':
        param = 'const ' + param

    # size?
    if parameter.pointer == True and c_intent(parameter) != 'IN':
        # Size is an output, or possibly an input and an output if
        # intent is INOUT
        size_type = 'int *'
    else:
        size_type = 'const int '

    required_size_list = parameter_size_list(parameter)[1]
    return ([size_type + size_name
        for size_name in required_size_list] + [param])


def parameter_size_list(parameter):
    """Get the list of dimension sizes for an array

    May be an integer constant or another variable name

    Sets the size_list, required_size_list and size_doxygen properties
    required_size_list does not include any dimensions that are constant
    size_doxygen has the same length as required_size_list
    """

    size_list = []
    required_size_list = []
    size_doxygen = []
    i = 0
    for dim in parameter.array_spec:
        if dim == ':':
            if parameter.required_sizes == 1:
                size_list.append('%sSize' % (parameter.name))
                if parameter.var_type == Parameter.CHARACTER:
                    size_doxygen.append('Length of %s string' % parameter.name)
                else:
                    size_doxygen.append('Length of %s' % parameter.name)
            elif parameter.var_type == Parameter.CHARACTER:
                try:
                    size_list.append(['%sNumStrings' % parameter.name,
                        '%sStringLength' % parameter.name][i])
                    size_doxygen.append(['Number of strings in %s' %
                        parameter.name,
                        'Length of strings in %s' % parameter.name][i])
                except IndexError:
                    raise ValueError(">2D arrays of strings not supported")
            else:
                size_list.append('%sSize%d' % (parameter.name, i + 1))
                size_doxygen.append('Size of dimension %d of %s' %
                    (i + 1, parameter.name))
            i += 1
            required_size_list.append(size_list[-1])
        else:
            size_list.append(dim)

    return (size_list, required_size_list, size_doxygen)


def parameter_doxygen_comments(parameter):
    """Return a list of doxygen comments corresponding to the list of
    parameters returned by to_c
    """

    size_doxygen = parameter_size_list(parameter)[2]

    return size_doxygen + [parameter.comment]


def type_to_c_header(typedef):
    """Return the struct and typedef definition for use in opencmiss.h"""

    output = 'struct %s_;\n' % typedef.name
    output += '/*>'
    output += '\n *>'.join(typedef.comment_lines)
    output += ' */\n'
    output += 'typedef struct %s_ *%s;\n\n' % (typedef.name, typedef.name)
    return output


def doxygen_to_c_header(doxygen):
    """Return the doxygen comment for use in opencmiss.h"""
    return '/*>' + doxygen.line + ' */\n'


def c_intent(parameter):
    """Work out intent for use in opencmiss_iron_c.f90"""

    intent = parameter.intent
    # C pointers to arrays must be passed by value
    if parameter.array_dims > 0 and not parameter.pointer:
        intent = 'IN'
    if parameter.array_dims == 0 and parameter.intent == 'INOUT':
        intent = 'IN'
    return intent


def _fix_length(line, max_length=132):
    """Add Fortran line continuations to break up long lines

    Tries to put the line continuation after a comma
    """

    first_join = ' &'
    second_join = '  & '

    # account for comments
    commentsplit = line.split('!')
    if len(commentsplit) < 2:
        content = line
        comment = ''
    else:
        content = commentsplit[0]
        comment = '!'.join(commentsplit[1:])
    if content.strip() == '':
        return line
    remaining_content = content
    indent = _get_indent(content)
    content = []
    while len(remaining_content) > max_length:
        break_pos = (remaining_content.rfind(
            ',', 0, max_length - len(first_join)) + 1)
        if break_pos < 0:
            sys.stderr.write("Error: Couldn't truncate line: %s\n" % line)
            exit(1)
        content.append(remaining_content[0:break_pos] + first_join)
        remaining_content = (indent + second_join +
            remaining_content[break_pos:])
    content.append(remaining_content)
    if comment:
        content.append('!' + comment)
    return '\n'.join(content)


def _get_indent(line):
    """Return the indentation in front of a line"""

    indent = line.replace(line.lstrip(), '')
    return indent


def _chain_iterable(iterables):
    """Implement itertools.chain.from_iterable for use in Python 2.5"""

    for it in iterables:
        for element in it:
            yield element


def _indent_lines(lines, indent_size=2, initial_indent=4):
    """Indent function content to show nesting of statements"""

    output = []
    indent = 0
    for line in lines:
        if (line.startswith('ELSE')
            or line.startswith('ENDIF')
            or line.startswith('ENDDO')):
            indent -= 1
        if line.strip():
            output.append(' ' * (initial_indent + indent * indent_size) + line)
        else:
            output.append('')
        if (line.startswith('IF')
            or line.startswith('ELSE')
            or line.startswith('DO')):
            indent += 1
    return output
