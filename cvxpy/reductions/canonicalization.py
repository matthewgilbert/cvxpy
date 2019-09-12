"""
Copyright 2013 Steven Diamond, 2017 Akshay Agrawal, 2017 Robin Verschueren

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from cvxpy import problems
from cvxpy.expressions import cvxtypes
from cvxpy.expressions.expression import Expression
from cvxpy.reductions import InverseData, Reduction, Solution
from cvxpy.reductions.utilities import tensor_mul
import scipy.sparse as sp


class Canonicalization(Reduction):
    """TODO(akshayka): Document this class."""

    def __init__(self, problem=None, canon_methods=None):
        super(Canonicalization, self).__init__(problem=problem)
        self.canon_methods = canon_methods

    def apply(self, problem):
        inverse_data = InverseData(problem)

        primal_tensor = {}
        for var in problem.variables():
            primal_tensor[var.id] = {var.id: sp.eye(var.size,
                                                    var.size,
                                                    format="csc")}
        inverse_data.primal_tensor = primal_tensor

        canon_objective, canon_constraints = self.canonicalize_tree(
            problem.objective)

        dual_tensor = {}
        for constraint in problem.constraints:
            # canon_constr is the constraint rexpressed in terms of
            # its canonicalized arguments, and aux_constr are the constraints
            # generated while canonicalizing the arguments of the original
            # constraint
            canon_constr, aux_constr = self.canonicalize_tree(
                constraint)
            canon_constraints += aux_constr + [canon_constr]
            for dv_old, dv_new in zip(constraint.dual_variables,
                                      canon_constr.dual_variables):
                dual_tensor[dv_old.id] = {dv_new.id: sp.eye(dv_new.size,
                                                            dv_new.size,
                                                            format="csc")}
        inverse_data.dual_tensor = dual_tensor

        new_problem = problems.problem.Problem(canon_objective,
                                               canon_constraints)
        return new_problem, inverse_data

    def invert(self, solution, inverse_data):
        pvars = tensor_mul(inverse_data.primal_tensor, solution.primal_vars)
        dvars = tensor_mul(inverse_data.dual_tensor, solution.dual_vars)
        # pvars = {vid: solution.primal_vars[vid] for vid in inverse_data.id_map
        #          if vid in solution.primal_vars}
        # dvars = {orig_id: solution.dual_vars[vid]
        #          for orig_id, vid in inverse_data.dv_id_map.items()
        #          if vid in solution.dual_vars}
        return Solution(solution.status, solution.opt_val, pvars, dvars,
                        solution.attr)

    def canonicalize_tree(self, expr):
        # TODO don't copy affine expressions?
        if type(expr) == cvxtypes.partial_problem():
            canon_expr, constrs = self.canonicalize_tree(
              expr.args[0].objective.expr)
            for constr in expr.args[0].constraints:
                canon_constr, aux_constr = self.canonicalize_tree(constr)
                constrs += [canon_constr] + aux_constr
        else:
            canon_args = []
            constrs = []
            for arg in expr.args:
                canon_arg, c = self.canonicalize_tree(arg)
                canon_args += [canon_arg]
                constrs += c
            canon_expr, c = self.canonicalize_expr(expr, canon_args)
            constrs += c
        return canon_expr, constrs

    def canonicalize_expr(self, expr, args):
        # Constant trees are collapsed,
        # but parameter trees are preserved.
        if isinstance(expr, Expression) and \
          (expr.is_constant() and not expr.parameters()):
            return expr, []
        elif type(expr) in self.canon_methods:
            return self.canon_methods[type(expr)](expr, args)
        else:
            return expr.copy(args), []
