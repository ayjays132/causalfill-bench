/* Standard Lean C ABI embedding of the public frontend, pinned to Lean 4.35.0.
 * References:
 * https://lean-lang.org/doc/reference/latest/Run-Time-Code/Foreign-Function-Interface/
 * Lean/Util/Path.lean: Lean.initSearchPath takes an explicit system root.
 * Lean/Elab/Frontend.lean: Lean.Elab.runFrontend, with trustLevel = 0 below.
 * No OS or runtime APIs are intercepted or replaced.
 */
#include <lean/lean.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern void lean_initialize(void);
extern char **lean_setup_args(int, char **);
extern lean_object *lean_enable_initializer_execution(void);
extern lean_object *l_Lean_initSearchPath(lean_object *, lean_object *);
extern lean_object *lean_name_mk_string(lean_object *, lean_object *);
extern lean_object *l_Lean_Options_empty;
extern lean_object *l_Lean_Options_setBool(lean_object *, lean_object *, uint8_t);
extern lean_object *l_Lean_Elab_runFrontend(
    lean_object *, lean_object *, lean_object *, lean_object *, uint32_t,
    lean_object *, lean_object *, uint8_t, lean_object *, lean_object *, uint8_t,
    lean_object *, lean_object *, lean_object *, lean_object *);

static void checked_io(lean_object *r) {
  if (!lean_io_result_is_ok(r)) {
    lean_io_result_show_error(r);
    lean_dec(r);
    exit(2);
  }
  lean_dec(r);
}

static lean_object *some(lean_object *value) {
  lean_object *r = lean_alloc_ctor(1, 1, 0);
  lean_ctor_set(r, 0, value);
  return r;
}

static lean_object *module_name(const char *name) {
  char *parts = strdup(name);
  lean_object *r = lean_box(0);
  for (char *part = strtok(parts, "."); part; part = strtok(NULL, "."))
    r = lean_name_mk_string(r, lean_mk_string(part));
  free(parts);
  return r;
}

int main(int argc, char **argv) {
  if (argc < 4 || argc > 5) {
    fprintf(stderr, "usage: lean_embed_frontend SYSROOT MODULE INPUT [OUTPUT_OLEAN]\n");
    return 2;
  }
  argv = lean_setup_args(argc, argv);
  FILE *file = fopen(argv[3], "rb");
  if (!file) { perror(argv[3]); return 2; }
  if (fseek(file, 0, SEEK_END) != 0) { perror("fseek"); return 2; }
  long length = ftell(file);
  if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { perror("ftell/fseek"); return 2; }
  char *input = malloc((size_t)length + 1);
  if (!input) { perror("malloc"); return 2; }
  if (fread(input, 1, (size_t)length, file) != (size_t)length) {
    perror("fread"); return 2;
  }
  input[length] = 0;
  fclose(file);
  if (memchr(input, 0, (size_t)length)) {
    fprintf(stderr, "source contains a NUL byte\n");
    free(input);
    return 2;
  }

  lean_initialize();
  lean_init_task_manager_using(1);
  checked_io(l_Lean_initSearchPath(lean_mk_string(argv[1]), lean_box(0)));
  lean_dec(lean_enable_initializer_execution());
  lean_io_mark_end_initialization();
  lean_inc(l_Lean_Options_empty);
  /* Public elaborator option: bound memory by checking declarations in order.
   * This changes scheduling only; the kernel trust level remains zero. */
  lean_object *options = l_Lean_Options_setBool(
      l_Lean_Options_empty, module_name("Elab.async"), 0);
  lean_object *result = l_Lean_Elab_runFrontend(
      lean_mk_string(input), options, lean_mk_string(argv[3]),
      module_name(argv[2]), 0,
      argc == 5 ? some(lean_mk_string(argv[4])) : lean_box(0),
      lean_box(0), 0, lean_mk_empty_array(), lean_mk_empty_array(), 0,
      lean_box(0), lean_box(0), lean_box(0), lean_box(0));
  free(input);
  if (!lean_io_result_is_ok(result)) {
    lean_io_result_show_error(result);
    lean_dec(result);
    return 2;
  }
  lean_object *environment = lean_io_result_get_value(result);
  int status = lean_is_scalar(environment) ? 1 : 0;
  lean_dec(result);
  return status;
}
