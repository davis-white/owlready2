# -*- coding: utf-8 -*-
# Owlready2
# Copyright (C) 2013-2017 Jean-Baptiste LAMY
# LIMICS (Laboratoire d'informatique médicale et d'ingénierie des connaissances en santé), UMR_S 1142
# University Paris 13, Sorbonne paris-Cité, Bobigny, France

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import owlready2
from owlready2.base      import *
from owlready2.namespace import *

  
class EntityClass(type):
  namespace = owlready
  
  def get_name(Class): return Class._name
  def set_name(Class, name):
    Class._name = name
    Class.namespace.world.refactor(Class.storid, "%s%s" % (Class.namespace.base_iri, name))
  name = property(get_name, set_name)
  
  def get_iri(Class): return "%s%s" % (Class.namespace.base_iri, Class._name)
  def set_iri(Class, new_iri):
    splitted = new_iri.rsplit("#", 1)
    if len(splitted) == 2:
      Class.namespace = Class.namespace.ontology.get_namespace("%s#" % splitted[0])
    else:
      splitted = new_iri.rsplit("/", 1)
      Class.namespace = Class.namespace.ontology.get_namespace("%s/" % splitted[0])
    Class._name = splitted[1]
    Class.namespace.world.refactor(Class.storid, new_iri)
  iri = property(get_iri, set_iri)
  
  
  _owl_type         = owl_class
  _rdfs_is_a        = rdfs_subclassof
  _owl_equivalent   = owl_equivalentclass
  _owl_disjointwith = owl_disjointwith
  _owl_alldisjoint  = owl_alldisjointclasses
  
  @staticmethod
  def _find_base_classes(is_a):
    bases = tuple(Class for Class in is_a if not isinstance(Class, ClassConstruct))
    if len(bases) > 1:
      # Must use sorted() and not sort(), because bases is accessed during the sort
      return tuple(sorted(bases, key = lambda Class: sum(issubclass_python(Other, Class) for Other in bases)))
    return bases or (Thing,)
  
  def mro(Class):
    try: return type.mro(Class)
    except TypeError:
      mro = [Class]
      for base in Class.__bases__:
        for base_mro in base.__mro__:
          if base_mro in mro: mro.remove(base_mro)
          mro.append(base_mro)
      return mro
    
  def __new__(MetaClass, name, superclasses, obj_dict):
    namespace = obj_dict.get("namespace") or CURRENT_NAMESPACES[-1] or superclasses[0].namespace
    storid    = obj_dict.get("storid")    or namespace.world.abbreviate("%s%s" % (namespace.base_iri, name))
    
    if "is_a" in obj_dict:
      _is_a = [*superclasses, *obj_dict["is_a"]]
      superclasses = MetaClass._find_base_classes(_is_a)
    else:
      if len(superclasses) > 1:
        _is_a = superclasses = MetaClass._find_base_classes(superclasses)
      else:
        _is_a = superclasses
        
    if LOADING:
      Class = namespace.world._entities.get (storid)
    else:
      for base in _is_a:
        if isinstance(base, ClassConstruct): base._set_ontology(namespace.ontology)
      Class = namespace.world._get_by_storid(storid)
      
    if Class is None:
      _is_a = CallbackList(_is_a, None, MetaClass._class_is_a_changed)
      obj_dict.update(
        _name          = name,
        namespace      = namespace,
        storid         = storid,
        is_a           = _is_a,
        _equivalent_to = None,
      )
      Class = namespace.world._entities[storid] = _is_a._obj = type.__new__(MetaClass, name, superclasses, obj_dict)
      
      if not LOADING:
        namespace.ontology.add_triple(storid, rdf_type, MetaClass._owl_type)
        for parent in _is_a: Class._add_is_a_triple(parent)
        
    else:
      if Class.is_a != _is_a: Class.is_a.extend([i for i in _is_a if not i in Class.is_a])
      
    if "equivalent_to" in obj_dict:
      equivalent_to = obj_dict.pop("equivalent_to")
      if isinstance(equivalent_to, list): Class.equivalent_to.extend(equivalent_to)
      
    return Class
  
  def _add_is_a_triple(Class, base):
    Class.namespace.ontology.add_triple(Class.storid, Class._rdfs_is_a, base.storid)
    
  def _del_is_a_triple(Class, base):
    Class.namespace.ontology.del_triple(Class.storid, Class._rdfs_is_a, base.storid)
    
  def __init__(Class, name, bases, obj_dict):
    for k, v in obj_dict.items():
      if k in SPECIAL_ATTRS: continue
      Prop = Class.namespace.world._props.get(k)
      if Prop is None:
        type.__setattr__(Class, k, v)
      else:
        delattr(Class, k) # Remove the value initially stored by obj_dict in __new__
        setattr(Class, k, v)
        
  def get_equivalent_to(Class):
    if Class._equivalent_to is None:
      eqs = [
        Class.namespace.world._to_python(o)
        for o in Class.namespace.world.get_transitive_sym(Class.storid, Class._owl_equivalent)
        if o != Class.storid
      ]
      Class._equivalent_to = CallbackList(eqs, Class, Class.__class__._class_equivalent_to_changed)
    return Class._equivalent_to
  
  def set_equivalent_to(Class, value): Class.equivalent_to.reinit(value)
  
  equivalent_to = property(get_equivalent_to, set_equivalent_to)
  
  def _class_equivalent_to_changed(Class, old):
    for Subclass in Class.descendants(True, True):
      _FUNCTIONAL_FOR_CACHE.pop(Subclass, None)
      
    new = frozenset(Class._equivalent_to)
    old = frozenset(old)
    
    for x in old - new:
      Class.namespace.ontology.del_triple(Class.storid, Class._owl_equivalent, x    .storid)
      Class.namespace.ontology.del_triple(x    .storid, Class._owl_equivalent, Class.storid)
      if isinstance(x, ClassConstruct): x._set_ontology(None)
      else: # Invalidate it
        for x2 in x.equivalent_to: x2._equivalent_to = None
        x._equivalent_to = None
        
    for x in new - old:
      if isinstance(x, ClassConstruct): x._set_ontology(Class.namespace.ontology)
      else: # Invalidate it
        for x2 in x.equivalent_to: x2._equivalent_to = None
        x._equivalent_to = None
      Class.namespace.ontology.add_triple(Class.storid, Class._owl_equivalent, x.storid)
      
    Class._equivalent_to = None # Invalidate, because the addition / removal may add its own equivalent.
    
  def __setattr__(Class, attr, value):
    if attr == "is_a":
      old = Class.is_a
      type.__setattr__(Class, "is_a", CallbackList(value, Class, Class.__class__._class_is_a_changed))
      Class._class_is_a_changed(old)
    type.__setattr__(Class, attr, value)
    
  def _class_is_a_changed(Class, old):
    for Subclass in Class.descendants(True, True):
      _FUNCTIONAL_FOR_CACHE.pop(Subclass, None)
      
    new = frozenset(Class.is_a)
    old = frozenset(old)
    for base in old - new:
      if not LOADING: Class._del_is_a_triple(base)
      if isinstance(base, ClassConstruct): base._set_ontology(None)
    Class.__bases__ = Class._find_base_classes(Class.is_a)
    for base in new - old:
      if isinstance(base, ClassConstruct): base._set_ontology(Class.namespace.ontology)
      if not LOADING: Class._add_is_a_triple(base)
      
  def disjoints(Class):
    for s, p, o, c in Class.namespace.world.get_quads(None, rdf_type, Class._owl_alldisjoint, None):
      onto = Class.namespace.world.graph.context_2_user_context(c)
      list_bnode = Class.namespace.world.get_triple_sp(s, owl_members)
      storids = set(onto._parse_list_as_rdf(list_bnode))
      if Class.storid in storids: yield onto._parse_bnode(s)
      
    for s, p, o, c in Class.namespace.world.get_quads(Class.storid, Class._owl_disjointwith, None, None):
      with LOADING: a = AllDisjoint((s, p, o), Class.namespace.world.graph.context_2_user_context(c), None)
      yield a # Must yield outside the with statement
      
    for s, p, o, c in Class.namespace.world.get_quads(None, Class._owl_disjointwith, Class.storid, None):
      with LOADING: a = AllDisjoint((s, p, o), Class.namespace.world.graph.context_2_user_context(c), None)
      yield a
    
  def ancestors(Class, include_self = True):
    s = set()
    Class._fill_ancestors(s, include_self)
    return s
  
  def descendants(Class, include_self = True, only_loaded = False):
    s = set()
    Class._fill_descendants(s, include_self, only_loaded)
    return s
  
  def _fill_ancestors(Class, s, include_self):
    if include_self:
      if not Class in s:
        s.add(Class)
        for equivalent in Class.equivalent_to:
          if isinstance(equivalent, EntityClass):
            if not equivalent in s: equivalent._fill_ancestors(s, True)
    for parent in Class.__bases__:
      if isinstance(parent, EntityClass):
        if not parent in s:
          parent._fill_ancestors(s, True)
          
  def _fill_descendants(Class, s, include_self, only_loaded = False):
    for x in Class.namespace.world.get_transitive_po(Class._rdfs_is_a, Class.storid):
      if not x.startswith("_"):
        if only_loaded:
          descendant = Class.namespace.world._entities.get(x)
          if descendant is None: continue
        else:
          descendant = Class.namespace.world._get_by_storid(x, None, Class.__class__, Class.namespace.ontology)
        if (descendant is Class) and (not include_self): continue
        if not descendant in s:
          s.add(descendant)
          for equivalent in descendant.equivalent_to:
            if isinstance(equivalent, Class.__class__):
              if not equivalent in s:
                equivalent._fill_descendants(s, True)
                
  def subclasses(Class, only_loaded = False):
    if only_loaded:
      r = []
      for x in Class.namespace.world.get_triples_po(Class._rdfs_is_a, Class.storid):
        if not x.startswith("_"):
          subclass = Class.namespace.world._entities.get(x)
          if not descendant is None: r.append(subclass)
      return r
      
    else:
      return [
        Class.namespace.world._get_by_storid(x, None, ThingClass, Class.namespace.ontology)
        for x in Class.namespace.world.get_triples_po(Class._rdfs_is_a, Class.storid)
        if not x.startswith("_")
      ]


def issubclass_owlready(Class, Parent_or_tuple):
  if issubclass_python(Class, Parent_or_tuple): return True
  if isinstance(Class, EntityClass):
    if not isinstance(Parent_or_tuple, tuple): Parent_or_tuple = (Parent_or_tuple,)
    parent_storids = { Parent.storid for Parent in Parent_or_tuple }
    
    Class_parents = set(Class.namespace.world.get_transitive_sp(Class.storid, Class._rdfs_is_a))
    if not parent_storids.isdisjoint(Class_parents): return True
    
    equivalent_storids = { Equivalent.storid for Parent in Parent_or_tuple for Equivalent in Parent.equivalent_to }
    if not equivalent_storids.isdisjoint(Class_parents): return True
    
  return False

issubclass = issubclass_owlready


class ThingClass(EntityClass):
  namespace = owlready
  
  def __instancecheck__(Class, instance):
    if not hasattr(instance, "storid"): return False
    if Class is Thing: return super().__instancecheck__(instance)
    for C in instance.is_a:
      if isinstance(C, EntityClass) and issubclass(C, Class): return True
    return False
  
  def _satisfied_by(Class, x):
    return (isinstance(x, EntityClass) and issubclass(x, Class)) or isinstance(x, Class)
  
  def _get_class_possible_relations(Class):
    for Prop in Class.namespace.world._reasoning_props.values():
      for domain in Prop.domains_indirect():
        if not domain._satisfied_by(Class): break
      else:
        yield Prop
        
  def instances(Class):
    for s in Class.namespace.world.get_triples_po(rdf_type, Class.storid):
      if not s.startswith("_"): yield Class.namespace.world._get_by_storid(s, None, Thing, Class.namespace.ontology)
      
      
  def __and__(a, b): return And([a, b])
  def __or__ (a, b): return Or ([a, b])
  def __invert__(a): return Not(a)
      
  def __rshift__(Domain, Range):
    import owlready2.property
    owlready2.property._next_domain_range = (Domain, Range)
    if isinstance(Range, ThingClass) or isinstance(Range, ClassConstruct):
      return owlready2.property.ObjectProperty
    else:
      return owlready2.property.DataProperty
    
  def __getattr__(Class, attr):
    Prop = Class.namespace.world._props.get(attr)
    if Prop is None: raise AttributeError("'%s' property is not defined." % attr)
    
    if issubclass_python(Prop, AnnotationProperty):
      # Do NOT cache as such in __dict__, to avoid inheriting annotations
      attr = "__%s" % attr
      values = Class.__dict__.get(attr)
      if values is None:
        values = ValueList((Class.namespace.ontology._to_python(o) for o in Class.namespace.world.get_triples_sp(Class.storid, Prop.storid)), Class, Prop)
        type.__setattr__(Class, attr, values)
      return values
    
    else:
      functional = Prop.is_functional_for(Class)
      
      if functional:
        for r in _inherited_property_value_restrictions(Class, Prop):
          if (r.type == VALUE): return r.value
        return None
      else:
        return RoleFilerList(
          (r.value for r in _inherited_property_value_restrictions(Class, Prop) if (r.type == VALUE)),
          Class, Prop)
      
      
  def constructs(Class, Prop = None):
    def _top_bn(s):
      try:
        construct = onto._parse_bnode(s)
        return construct
      except:
        for relation in [rdf_first, rdf_rest, owl_complementof, owl_unionof, owl_intersectionof, owl_onclass]:
          s2 = Class.namespace.world.get_triple_po(relation, s)
          if not s2 is None:
            return _top_bn(s2)
          
    if Prop: Prop = Prop.storid
    for s,p,o,c in Class.namespace.world.get_quads(None, Prop, Class.storid, None):
      if s.startswith("_"):
        
        onto = Class.namespace.world.graph.context_2_user_context(c)
        construct = _top_bn(s)
        if not construct is None:
          yield construct
          
  # Role-fillers as class properties
  
  #def _get_prop_for_self(self, attr):
  #  Prop = Class.namespace.world._reasoning_props.get(attr)
  #  if Prop is None: raise AttributeError("'%s' property is not defined." % attr)
  #  for domain in Prop.domain:
  #    if not domain._satisfied_by(self): raise AttributeError("'%s' property has incompatible domain for %s." % (attr, self))
  #  return Prop
  
  def _on_class_prop_changed(Class, Prop, old, new):
    old     = set(old)
    new     = set(new)
    removed = old - new
    inverse = Prop.inverse_property
    
    if removed:
      for r in list(_inherited_property_value_restrictions(Class, Prop)):
        if r.type == VALUE:
          if (r.value in removed) and (r in Class.is_a):
            Class.is_a.remove(r)
            #if inverse:
            if isinstance(Prop, ObjectPropertyClass):
              for r2 in r.value.is_a:
                if isinstance(r2, Restriction) and ((r2.property is inverse) or (isinstance(r2.property, Inverse) and (r2.property.property is Prop))) and (r2.type == SOME) and (r2.value is Class):
                  r.value.is_a.remove(r2)
                  break
                
    for v in new - old:
      Class.is_a.append(Prop.value(v))
      #if inverse:
      if isinstance(Prop, ObjectPropertyClass):
        v.is_a.append(Inverse(Prop).some(Class))
        
  def __setattr__(Class, attr, value):
    if attr in SPECIAL_ATTRS:
      super().__setattr__(attr, value)
      return
    
    Prop = Class.namespace.world._props.get(attr)
    
    if Prop.is_functional_for(Class):
      for r in _inherited_property_value_restrictions(Class, Prop):
        if (r.type == VALUE): old = [r.value]; break
      else: old = []
      if value is None: Class._on_class_prop_changed(Prop, old, [])
      else:             Class._on_class_prop_changed(Prop, old, [value])
    else:
      getattr(Class, attr).reinit(value)
      

class RoleFilerList(CallbackListWithLanguage):
  __slots__ = ["_Prop"]
  def __init__(self, l, obj, Prop):
    list.__init__(self, l)
    self._obj  = obj
    self._Prop = Prop
    
  def _callback(self, obj, old): self._obj._on_class_prop_changed(self._Prop, old, self)
      


def _inherited_property_value_restrictions(Class, Prop):
  if isinstance(Class, Restriction):
    yield Class
    return
  
  for parent in itertools.chain(Class.is_a, Class.equivalent_to):
    if isinstance(parent, Restriction) and (parent.property is Prop):
      yield parent
    if isinstance(parent, And):
      for Class2 in parent.Classes: yield from _inherited_property_value_restrictions(Class2, Prop)
    if isinstance(parent, EntityClass): yield from _inherited_property_value_restrictions(parent, Prop)