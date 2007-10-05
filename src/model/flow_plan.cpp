/***************************************************************************
  file : $URL$
  version : $LastChangedRevision$  $LastChangedBy$
  date : $LastChangedDate$
  email : jdetaeye@users.sourceforge.net
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 * Copyright (C) 2007 by Johan De Taeye                                    *
 *                                                                         *
 * This library is free software; you can redistribute it and/or modify it *
 * under the terms of the GNU Lesser General Public License as published   *
 * by the Free Software Foundation; either version 2.1 of the License, or  *
 * (at your option) any later version.                                     *
 *                                                                         *
 * This library is distributed in the hope that it will be useful,         *
 * but WITHOUT ANY WARRANTY; without even the implied warranty of          *
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser *
 * General Public License for more details.                                *
 *                                                                         *
 * You should have received a copy of the GNU Lesser General Public        *
 * License along with this library; if not, write to the Free Software     *
 * Foundation Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA *
 *                                                                         *
 ***************************************************************************/


#define FREPPLE_CORE
#include "frepple/model.h"
namespace frepple
{


DECLARE_EXPORT FlowPlan::FlowPlan (OperationPlan *opplan, const Flow *f)
    : TimeLine<FlowPlan>::EventChangeOnhand(
      f->getQuantity() * opplan->getQuantity())
{
  assert(opplan);
  fl = const_cast<Flow*>(f);
  oper = opplan;
  nextFlowPlan = opplan->firstflowplan;
  opplan->firstflowplan = this;
  f->getBuffer()->flowplans.insert(this);

  // Mark the operation and buffer as having changed. This will trigger the
  // recomputation of their problems
  f->getBuffer()->setChanged();
  f->getOperation()->setChanged();
}


DECLARE_EXPORT void FlowPlan::update()
{
  // Update the timeline data structure
  fl->getBuffer()->flowplans.setQuantity(
    this,
    oper->getQuantity() * fl->getQuantity()
  );

  // Mark the operation and buffer as having changed. This will trigger the
  // recomputation of their problems
  fl->getBuffer()->setChanged();
  fl->getOperation()->setChanged();

  // Check validity
  assert( check() );
}


DECLARE_EXPORT bool FlowPlan::check() const
{
  // Quantity must match with the operationplan
  if (fabs(oper->getQuantity() * fl->getQuantity() - getQuantity())
      > ROUNDING_ERROR)
    return false;
  else
    return true;
}


// Remember that this method only superficially looks like a normal
// writeElement() method.
DECLARE_EXPORT void FlowPlan::writeElement(XMLOutput *o, const XMLtag& tag, mode m) const
{
  o->BeginObject(tag);
  o->writeElement(Tags::tag_date, getDate());
  o->writeElement(Tags::tag_quantity, getQuantity());
  o->writeElement(Tags::tag_onhand, getOnhand());
  o->writeElement(Tags::tag_minimum, getMin());
  o->writeElement(Tags::tag_maximum, getMax());
  if (!dynamic_cast<OperationPlan*>(o->getCurrentObject()))
    o->writeElement(Tags::tag_operation_plan, &*getOperationPlan());

  // Write pegging info
  if (o->getContentType() == XMLOutput::PLANDETAIL)
  {
    // Write the upstream pegging
    PeggingIterator k(this, false);
    if (k) --k;
    for (; k; --k)
    {
      o->BeginObject(Tags::tag_pegging, Tags::tag_level, k.getLevel());
      o->writeElement(Tags::tag_quantity, k.getQuantityDemand());
      o->writeElement(Tags::tag_factor, k.getFactor());
      if (!k.getPegged()) o->writeElement(Tags::tag_id, "unpegged");
      o->writeElement(Tags::tag_buffer, Tags::tag_name, k.getBuffer()->getName());
      if (k.getConsumingOperationplan())
        o->writeElement(Tags::tag_consuming,
          Tags::tag_id, k.getConsumingOperationplan()->getIdentifier(),
          Tags::tag_operation, k.getConsumingOperationplan()->getOperation()->getName());
      if (k.getProducingOperationplan())
        o->writeElement(Tags::tag_producing,
          Tags::tag_id, k.getProducingOperationplan()->getIdentifier(),
          Tags::tag_operation, k.getProducingOperationplan()->getOperation()->getName());
      o->writeElement(Tags::tag_dates, DateRange(k.getProducingDate(),k.getConsumingDate()));
      o->EndObject(Tags::tag_pegging);
    }

    // Write the downstream pegging
    PeggingIterator l(this, true);
    if (l) ++l;
    for (; l; ++l)
    {
      o->BeginObject(Tags::tag_pegging, Tags::tag_level, l.getLevel());
      o->writeElement(Tags::tag_quantity, l.getQuantity());
      o->writeElement(Tags::tag_factor, l.getFactor());
      if (!l.getPegged()) o->writeElement(Tags::tag_id, "unpegged");
      o->writeElement(Tags::tag_buffer, Tags::tag_name, l.getBuffer()->getName());
      if (l.getConsumingOperationplan())
        o->writeElement(Tags::tag_consuming,
          Tags::tag_id, l.getConsumingOperationplan()->getIdentifier(),
          Tags::tag_operation, l.getConsumingOperationplan()->getOperation()->getName());
      if (l.getProducingOperationplan())
        o->writeElement(Tags::tag_producing,
          Tags::tag_id, l.getProducingOperationplan()->getIdentifier(),
          Tags::tag_operation, l.getProducingOperationplan()->getOperation()->getName());
      o->writeElement(Tags::tag_dates, DateRange(l.getProducingDate(),l.getConsumingDate()));
      o->EndObject(Tags::tag_pegging);
    }
  }

  o->EndObject(tag);
}

}
