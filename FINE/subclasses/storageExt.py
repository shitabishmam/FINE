from FINE.component import Component, ComponentModel
from FINE.storage import Storage, StorageModel
from FINE import utils
import pyomo.environ as pyomo
import warnings
import pandas as pd


class StorageExt(Storage):
    """
    Doc
    """
    def __init__(self, esM, name, commodity, chargeRate=1, dischargeRate=1,
                 chargeEfficiency=1, dischargeEfficiency=1, selfDischarge=0, cyclicLifetime=None,
                 stateOfChargeMin=0, stateOfChargeMax=1,
                 hasCapacityVariable=True, capacityVariableDomain='continuous', capacityPerPlantUnit=1,
                 hasIsBuiltBinaryVariable=False, bigM=None, doPreciseTsaModeling=False,
                 chargeOpRateMax=None, chargeOpRateFix=None, chargeTsaWeight=1,
                 dischargeOpRateMax=None, dischargeOpRateFix=None, dischargeTsaWeight=1,
                 stateOfChargeOpRateMax=None, stateOfChargeOpRateFix=None, stateOfChargeTsaWeight=1,
                 isPeriodicalStorage=False,
                 locationalEligibility=None, capacityMin=None, capacityMax=None, sharedPotentialID=None,
                 capacityFix=None, isBuiltFix=None,
                 investPerCapacity=0, investIfBuilt=0, opexPerChargeOperation=0,
                 opexPerDischargeOperation=0, opexPerCapacity=0, opexIfBuilt=0, interestRate=0.08, economicLifetime=10):
        """
        Constructor for creating an Storage class instance.
        The Storage component specific input arguments are described below. The general component
        input arguments are described in the Component class.

        **Default arguments:**

        :param stateOfChargeOpRateMax: if specified indicates a maximum state of charge for each location and
            each time step by a positive float. If hasCapacityVariable is set to True, the values are given
            relative to the installed capacities (i.e. in that case a value of 1 indicates a utilization of
            100% of the capacity). If hasCapacityVariable is set to False, the values are given as absolute
            values in form of the commodityUnit, referring to the commodity stored in the component at the
            beginning of one time step.
            |br| * the default value is None
        :type stateOfChargeOpRateMax: None or Pandas DataFrame with positive (>= 0) entries. The row indices have
            to match the in the energy system model  specified time steps. The column indices have to match the
            in the energy system model specified locations.

        :param stateOfChargeOpRateFix: if specified indicates a fixed state of charge for each location and
            each time step by a positive float. If hasCapacityVariable is set to True, the values are given
            relative to the installed capacities (i.e. in that case a value of 1 indicates a utilization of
            100% of the capacity). If hasCapacityVariable is set to False, the values are given as absolute
            values in form of the commodityUnit, referring to the commodity stored in the component at the
            beginning of one time step.
            |br| * the default value is None
        :type stateOfChargeOpRateFix: None or Pandas DataFrame with positive (>= 0) entries. The row indices have
            to match the in the energy system model specified time steps. The column indices have to match the
            in the energy system model specified locations.

        :param stateOfChargeTsaWeight: weight with which the stateOfChargeOpRate (max/fix) time series of the
            component should be considered when applying time series aggregation.
            |br| * the default value is 1
        :type stateOfChargeTsaWeight: positive (>= 0) float
        """
        Storage.__init__(self, esM, name, commodity, chargeRate, dischargeRate, chargeEfficiency, dischargeEfficiency,
                         selfDischarge, cyclicLifetime, stateOfChargeMin, stateOfChargeMax, hasCapacityVariable,
                         capacityVariableDomain, capacityPerPlantUnit, hasIsBuiltBinaryVariable, bigM,
                         doPreciseTsaModeling, chargeOpRateMax, chargeOpRateFix, chargeTsaWeight, dischargeOpRateMax,
                         dischargeOpRateFix, dischargeTsaWeight, isPeriodicalStorage, locationalEligibility,
                         capacityMin, capacityMax, sharedPotentialID, capacityFix, isBuiltFix, investPerCapacity,
                         investIfBuilt, opexPerChargeOperation, opexPerDischargeOperation, opexPerCapacity,
                         opexIfBuilt, interestRate, economicLifetime)

        # Set location-specific operation parameters (Charging rate, discharging rate, state of charge rate)
        # and time series aggregation weighting factor

        # The i-th state of charge (SOC) refers to the SOC before the i-th time step
        if stateOfChargeOpRateMax is not None and stateOfChargeOpRateFix is not None:
            stateOfChargeOpRateMax = None
            warnings.warn('If stateOfChargeOpRateFix is specified, the stateOfChargeOpRateMax parameter is not +'
                          'required.\nThe stateOfChargeOpRateMax time series was set to None.')
        if (stateOfChargeOpRateMax is not None or stateOfChargeOpRateFix is not None) and not doPreciseTsaModeling:
            self.doPreciseTsaModeling = True
            warnings.warn('Warning only relevant when time series aggregation is used in optimization:\n' +
                          'If stateOfChargeOpRateFix or the stateOfChargeOpRateMax parameter are specified,\n' +
                          'the modeling is set to precise.')
        if stateOfChargeOpRateMax is not None:
            warnings.warn('Warning only relevant when time series aggregation is used in optimization:\n' +
                          'Setting the stateOfChargeOpRateMax parameter might lead to unwanted modeling behavior\n' +
                          'and should be handled with caution.')
        if stateOfChargeOpRateFix is not None and not isPeriodicalStorage:
            self.isPeriodicalStorage = True
            warnings.warn('Warning only relevant when time series aggregation is used in optimization:\n' +
                          'If the stateOfChargeOpRateFix parameter is specified, the storage\n' +
                          'is set to isPeriodicalStorage).')
        utils.checkOperationTimeSeriesInputParameters(esM, stateOfChargeOpRateMax, locationalEligibility)
        utils.checkOperationTimeSeriesInputParameters(esM, stateOfChargeOpRateFix, locationalEligibility)

        self.fullStateOfChargeOpRateMax = utils.setFormattedTimeSeries(stateOfChargeOpRateMax)
        self.aggregatedStateOfChargeOpRateMax = None
        self.stateOfChargeOpRateMax = None

        self.fullStateOfChargeOpRateFix = utils.setFormattedTimeSeries(stateOfChargeOpRateFix)
        self.aggregatedStateOfChargeOpRateFix = None
        self.stateOfChargeOpRateFix = None

        utils.isPositiveNumber(stateOfChargeTsaWeight)
        self.stateOfChargeTsaWeight = stateOfChargeTsaWeight

        # Set locational eligibility
        timeSeriesData = None
        tsNb = sum([0 if data is None else 1 for data in [chargeOpRateMax, chargeOpRateFix, dischargeOpRateMax,
                    dischargeOpRateFix, stateOfChargeOpRateMax, stateOfChargeOpRateFix]])
        if tsNb > 0:
            timeSeriesData = sum([data for data in [chargeOpRateMax, chargeOpRateFix, dischargeOpRateMax,
                                  dischargeOpRateFix, stateOfChargeOpRateMax, stateOfChargeOpRateFix]
                                  if data is not None])
        self.locationalEligibility = \
            utils.setLocationalEligibility(esM, self.locationalEligibility, self.capacityMax, self.capacityFix,
                                           self.isBuiltFix, self.hasCapacityVariable, timeSeriesData)

    def addToEnergySystemModel(self, esM):
        super().addToEnergySystemModel(esM)

    def setTimeSeriesData(self, hasTSA):
        self.chargeOpRateMax = self.aggregatedChargeOpRateMax if hasTSA else self.fullChargeOpRateMax
        self.chargeOpRateFix = self.aggregatedChargeOpRateFix if hasTSA else self.fullChargeOpRateFix
        self.dischargeOpRateMax = self.aggregatedChargeOpRateMax if hasTSA else self.fullDischargeOpRateMax
        self.dischargeOpRateFix = self.aggregatedChargeOpRateFix if hasTSA else self.fullDischargeOpRateFix
        self.stateOfChargeOpRateMax = self.aggregatedStateOfChargeOpRateMax if hasTSA \
            else self.fullStateOfChargeOpRateMax
        self.stateOfChargeOpRateFix = self.aggregatedStateOfChargeOpRateFix if hasTSA \
            else self.fullStateOfChargeOpRateFix

    def getDataForTimeSeriesAggregation(self):
        weightDict, data = {}, []
        I = [(self.fullChargeOpRateFix, self.fullChargeOpRateMax, 'chargeRate_', self.chargeTsaWeight),
             (self.fullDischargeOpRateFix, self.fullDischargeOpRateMax, 'dischargeRate_', self.dischargeTsaWeight),
             (self.stateOfChargeOpRateFix, self.stateOfChargeOpRateMax, '_SOCRate_', self.stateOfChargeTsaWeight)]

        for rateFix, rateMax, rateName, rateWeight in I:
            weightDict, data = self.prepareTSAInput(rateFix, rateMax, rateName, rateWeight, weightDict, data)
        return (pd.concat(data, axis=1), weightDict) if data else (None, {})

    def setAggregatedTimeSeriesData(self, data):

        self.aggregatedChargeOpRateFix = self.getTSAOutput(self.fullChargeOpRateFix, 'chargeRate_', data)
        self.aggregatedChargeOpRateMax = self.getTSAOutput(self.fullChargeOpRateMax, 'chargeRate_', data)

        self.aggregatedDischargeOpRateFix = self.getTSAOutput(self.fullDischargeOpRateFix, 'dischargeRate_', data)
        self.aggregatedDischargeOpRateMax = self.getTSAOutput(self.fullDischargeOpRateMax, 'dischargeRate_', data)

        self.aggregatedStateOfChargeOpRateFix = self.getTSAOutput(self.fullStateOfChargeOpRateFix, '_SOCRate_', data)
        self.aggregatedStateOfChargeOpRateMax = self.getTSAOutput(self.fullStateOfChargeOpRateMax, '_SOCRate_', data)


class StorageExtModel(StorageModel):
    """ Doc """

    def __init__(self):
        self.abbrvName = 'stor'
        self.dimension = '1dim'
        self.componentsDict = {}
        self.capacityVariablesOptimum, self.isBuiltVariablesOptimum = None, None
        self.chargeOperationVariablesOptimum, self.dischargeOperationVariablesOptimum = None, None
        self.stateOfChargeOperationVariablesOptimum = None
        self.optSummary = None

    ####################################################################################################################
    #                                            Declare sparse index sets                                             #
    ####################################################################################################################

    def declareSets(self, esM, pyM):
        """ Declares sets and dictionaries """

        super().declareSets(esM, pyM)

        # * State of charge operation TODO check if also applied for simple SOC modeling
        self.declareOperationModeSets(pyM, 'stateOfChargeOpConstrSet',
                                      'stateOfChargeOpRateMax', 'stateOfChargeOpRateFix')

    ####################################################################################################################
    #                                                Declare variables                                                 #
    ####################################################################################################################

    def declareVariables(self, esM, pyM):
        """ Declares design and operation variables """

        super().declareVariables(esM, pyM)

    ####################################################################################################################
    #                                          Declare component constraints                                           #
    ####################################################################################################################

    def operationModeSOCwithTSA1(self, pyM, esM):
        """
        State of charge [energyUnit] limited by the installed capacity [powerUnit] and the relative maximum
        state of charge
        """
        compDict, abbrvName = self.componentsDict, self.abbrvName
        SOCinter = getattr(pyM, 'stateOfChargeInterPeriods_' + abbrvName)
        SOC, capVar = getattr(pyM, 'stateOfCharge_' + abbrvName), getattr(pyM, 'cap_' + abbrvName)
        constrSet1 = getattr(pyM, 'stateOfChargeOpConstrSet1_' + abbrvName)

        def SOCMaxPrecise1(pyM, loc, compName, pInter, t):
            if compDict[compName].doPreciseTsaModeling:
                return (SOCinter[loc, compName, pInter] *
                        ((1 - compDict[compName].selfDischarge) ** (t * esM.hoursPerTimeStep)) +
                        SOC[loc, compName, esM.periodsOrder[pInter], t]
                        <= capVar[loc, compName] * compDict[compName].stateOfChargeMax)
            else:
                return pyomo.Constraint.Skip
        setattr(pyM, 'ConstrSOCMaxPrecise1_' + abbrvName,
                pyomo.Constraint(constrSet1, esM.periods, esM.timeStepsPerPeriod, rule=SOCMaxPrecise1))

    def operationModeSOCwithTSA2(self, pyM, esM):
        """
        State of charge [energyUnit] equal to the installed capacity [energyUnit] multiplied by state of charge
        time series [energyUnit/energyUnit]
        """
        compDict, abbrvName = self.componentsDict, self.abbrvName
        SOCinter = getattr(pyM, 'stateOfChargeInterPeriods_' + abbrvName)
        SOC, capVar = getattr(pyM, 'stateOfCharge_' + abbrvName), getattr(pyM, 'cap_' + abbrvName)
        constrSet2 = getattr(pyM, 'stateOfChargeOpConstrSet2_' + abbrvName)

        def SOCMaxPrecise2(pyM, loc, compName, pInter, t):
            if compDict[compName].doPreciseTsaModeling:
                return (SOCinter[loc, compName, pInter] *
                        ((1 - compDict[compName].selfDischarge) ** (t * esM.hoursPerTimeStep)) +
                        SOC[loc, compName, esM.periodsOrder[pInter], t]
                        == capVar[loc, compName] *
                        compDict[compName].stateOfChargeOpRateFix[loc][esM.periodsOrder[pInter], t])
            else:
                return pyomo.Constraint.Skip
        setattr(pyM, 'ConstrSOCMaxPrecise2_' + abbrvName,
                pyomo.Constraint(constrSet2, esM.periods, esM.timeStepsPerPeriod, rule=SOCMaxPrecise2))

    def operationModeSOCwithTSA3(self, pyM, esM):
        """
        State of charge [energyUnit] limited by the installed capacity [energyUnit] multiplied by state of charge
        time series [energyUnit/energyUnit]
        """
        compDict, abbrvName = self.componentsDict, self.abbrvName
        SOCinter = getattr(pyM, 'stateOfChargeInterPeriods_' + abbrvName)
        SOC, capVar = getattr(pyM, 'stateOfCharge_' + abbrvName), getattr(pyM, 'cap_' + abbrvName)
        constrSet3 = getattr(pyM, 'stateOfChargeOpConstrSet3_' + abbrvName)

        def SOCMaxPrecise3(pyM, loc, compName, pInter, t):
            if compDict[compName].doPreciseTsaModeling:
                return (SOCinter[loc, compName, pInter] *
                        ((1 - compDict[compName].selfDischarge) ** (t * esM.hoursPerTimeStep)) +
                        SOC[loc, compName, esM.periodsOrder[pInter], t]
                        <= capVar[loc, compName] *
                        compDict[compName].stateOfChargeOpRateMax[loc][esM.periodsOrder[pInter], t])
            else:
                return pyomo.Constraint.Skip
        setattr(pyM, 'ConstrSOCMaxPrecise3_' + abbrvName,
                pyomo.Constraint(constrSet3, esM.periods, esM.timeStepsPerPeriod, rule=SOCMaxPrecise3))

    def operationModeSOCwithTSA4(self, pyM, esM):
        """ Operation [energyUnit] equal to the operation time series [energyUnit] """
        compDict, abbrvName = self.componentsDict, self.abbrvName
        SOCinter = getattr(pyM, 'stateOfChargeInterPeriods_' + abbrvName)
        SOC = getattr(pyM, 'stateOfCharge_' + abbrvName)
        constrSet4 = getattr(pyM, 'stateOfChargeOpConstrSet4_' + abbrvName)

        def SOCMaxPrecise4(pyM, loc, compName, pInter, t):
            if compDict[compName].doPreciseTsaModeling:
                return (SOCinter[loc, compName, pInter] *
                        ((1 - compDict[compName].selfDischarge) ** (t * esM.hoursPerTimeStep)) +
                        SOC[loc, compName, esM.periodsOrder[pInter], t]
                        == compDict[compName].stateOfChargeOpRateFix[loc][esM.periodsOrder[pInter], t])
            else:
                return pyomo.Constraint.Skip
        setattr(pyM, 'ConstrSOCMaxPrecise4_' + abbrvName,
                pyomo.Constraint(constrSet4, esM.periods, esM.timeStepsPerPeriod, rule=SOCMaxPrecise4))

    def operationModeSOCwithTSA5(self, pyM, esM):
        """ Operation [energyUnit] limited by the operation time series [energyUnit] """
        compDict, abbrvName = self.componentsDict, self.abbrvName
        SOCinter = getattr(pyM, 'stateOfChargeInterPeriods_' + abbrvName)
        SOC = getattr(pyM, 'stateOfCharge_' + abbrvName)
        constrSet5 = getattr(pyM, 'stateOfChargeOpConstrSet5_' + abbrvName)

        def SOCMaxPrecise5(pyM, loc, compName, pInter, t):
            if compDict[compName].doPreciseTsaModeling:
                return (SOCinter[loc, compName, pInter] *
                        ((1 - compDict[compName].selfDischarge) ** (t * esM.hoursPerTimeStep)) +
                        SOC[loc, compName, esM.periodsOrder[pInter], t]
                        <= compDict[compName].stateOfChargeOpRateMax[loc][esM.periodsOrder[pInter], t])
            else:
                return pyomo.Constraint.Skip
        setattr(pyM, 'ConstrSOCMaxPrecise5_' + abbrvName,
                pyomo.Constraint(constrSet5, esM.periods, esM.timeStepsPerPeriod, rule=SOCMaxPrecise5))

    def declareComponentConstraints(self, esM, pyM):
        """ Declares time independent and dependent constraints"""

        ################################################################################################################
        #                                    Declare time independent constraints                                      #
        ################################################################################################################

        # Determine the components' capacities from the number of installed units
        self.capToNbReal(pyM)
        # Determine the components' capacities from the number of installed units
        self.capToNbInt(pyM)
        # Enforce the consideration of the binary design variables of a component
        self.bigM(pyM)
        # Enforce the consideration of minimum capacities for components with design decision variables
        self.capacityMinDec(pyM)
        # Sets, if applicable, the installed capacities of a component
        self.capacityFix(pyM)
        # Sets, if applicable, the binary design variables of a component
        self.designBinFix(pyM)

        ################################################################################################################
        #                                      Declare time dependent constraints                                      #
        ################################################################################################################

        # Constraint for connecting the state of charge with the charge and discharge operation
        self.connectSOCs(pyM, esM)

        #                              Constraints for enforcing charging operation modes                              #

        # Charging of storage [energyUnit] limited by the installed capacity [energyUnit] multiplied by the hours per
        # time step [h] and the charging rate factor [powerUnit/energyUnit]
        self.operationMode1(pyM, esM, 'ConstrCharge', 'chargeOpConstrSet', 'chargeOp', 'chargeRate')
        # Charging of storage [energyUnit] limited by the installed capacity [energyUnit] multiplied by the hours per
        # time step [h] and the charging operation time series [powerUnit/energyUnit]
        self.operationMode2(pyM, esM, 'ConstrCharge', 'chargeOpConstrSet', 'chargeOp')
        # Charging of storage [energyUnit] equal to the installed capacity [energyUnit] multiplied by the hours per
        # time step [h] and the charging operation time series [powerUnit/energyUnit]
        self.operationMode3(pyM, esM, 'ConstrCharge', 'chargeOpConstrSet', 'chargeOp')
        # Operation [energyUnit] limited by the operation time series [energyUnit]
        self.operationMode4(pyM, esM, 'ConstrCharge', 'chargeOpConstrSet', 'chargeOp')
        # Operation [energyUnit] equal to the operation time series [energyUnit]
        self.operationMode5(pyM, esM, 'ConstrCharge', 'chargeOpConstrSet', 'chargeOp')

        #                             Constraints for enforcing discharging operation modes                            #

        # Discharging of storage [energyUnit] limited by the installed capacity [energyUnit] multiplied by the hours per
        # time step [h] and the discharging rate factor [powerUnit/energyUnit]
        self.operationMode1(pyM, esM, 'ConstrDischarge', 'dischargeOpConstrSet', 'dischargeOp', 'dischargeRate')
        # Discharging of storage [energyUnit] limited by the installed capacity [energyUnit] multiplied by the hours per
        # time step [h] and the charging operation time series [powerUnit/energyUnit]
        self.operationMode2(pyM, esM, 'ConstrDischarge', 'dischargeOpConstrSet', 'dischargeOp')
        # Discharging of storage [energyUnit] equal to the installed capacity [energyUnit] multiplied by the hours per
        # time step [h] and the charging operation time series [powerUnit/energyUnit]
        self.operationMode3(pyM, esM, 'ConstrDischarge', 'dischargeOpConstrSet', 'dischargeOp')
        # Operation [energyUnit] limited by the operation time series [energyUnit]
        self.operationMode4(pyM, esM, 'ConstrDischarge', 'dischargeOpConstrSet', 'dischargeOp')
        # Operation [energyUnit] equal to the operation time series [energyUnit]
        self.operationMode5(pyM, esM, 'ConstrDischarge', 'dischargeOpConstrSet', 'dischargeOp')

        # Cyclic constraint enforcing that all storages have the same state of charge at the the beginning of the first
        # and the end of the last time step
        self.cyclicState(pyM, esM)

        # Constraint for limiting the number of full cycle equivalents to stay below cyclic lifetime
        self.cyclicLifetime(pyM, esM)

        if pyM.hasTSA:
            # The state of charge at the end of each period is equivalent to the state of charge of the period before it
            # (minus its self discharge) plus the change in the state of charge which happened during the typical
            # # period which was assigned to that period
            self.connectInterPeriodSOC(pyM, esM)
            # The (virtual) state of charge at the beginning of a typical period is zero
            self.intraSOCstart(pyM, esM)
            # If periodic storage is selected, the states of charge between periods have the same value
            self.equalInterSOC(pyM, esM)

        # Ensure that the state of charge is within the operating limits of the installed capacities
        if not pyM.hasTSA:
            #              Constraints for enforcing a state of charge operation mode within given limits              #

            # State of charge [energyUnit] limited by the installed capacity [energyUnit] and the relative maximum
            # state of charge
            self.operationMode1(pyM, esM, 'ConstrSOCMax', 'stateOfChargeOpConstrSet', 'stateOfCharge',
                                'stateOfChargeMax', isStateOfCharge=True)
            # State of charge [energyUnit] equal to the installed capacity [energyUnit] multiplied by state of charge
            # time series [energyUnit/energyUnit]
            self.operationMode2(pyM, esM, 'ConstrSOCMax', 'stateOfChargeOpConstrSet', 'stateOfCharge',
                                isStateOfCharge=True)
            # State of charge [energyUnit] limited by the installed capacity [energyUnit] multiplied by state of charge
            # time series [energyUnit/energyUnit]
            self.operationMode3(pyM, esM, 'ConstrSOCMax', 'stateOfChargeOpConstrSet', 'stateOfCharge',
                                isStateOfCharge=True)
            # Operation [energyUnit] equal to the operation time series [energyUnit]
            self.operationMode4(pyM, esM, 'ConstrSOCMax', 'stateOfChargeOpConstrSet', 'stateOfCharge')
            # Operation [energyUnit] limited by the operation time series [energyUnit]
            self.operationMode5(pyM, esM, 'ConstrSOCMax', 'stateOfChargeOpConstrSet', 'stateOfCharge')

            # The state of charge [energyUnit] has to be larger than the installed capacity [energyUnit] multiplied
            # with the relative minimum state of charge
            self.minSOC(pyM)

        else:
            #                       Simplified version of the state of charge limitation control                       #
            #           (The error compared to the precise version is small in cases of small selfDischarge)           #
            self.limitSOCwithSimpleTsa(pyM, esM)

            #                        Precise version of the state of charge limitation control                         #

            # Constraints for enforcing a state of charge operation within given limits

            # State of charge [energyUnit] limited by the installed capacity [energyUnit] and the relative maximum
            # state of charge
            self.operationModeSOCwithTSA1(pyM, esM)
            # State of charge [energyUnit] equal to the installed capacity [energyUnit] multiplied by state of charge
            # time series [energyUnit/energyUnit]
            self.operationModeSOCwithTSA2(pyM, esM)
            # State of charge [energyUnit] limited by the installed capacity [energyUnit] multiplied by state of charge
            # time series [energyUnit/energyUnit]
            self.operationModeSOCwithTSA3(pyM, esM)
            # Operation [energyUnit] equal to the operation time series [energyUnit]
            self.operationModeSOCwithTSA4(pyM, esM)
            # Operation [energyUnit] limited by the operation time series [energyUnit]
            self.operationModeSOCwithTSA5(pyM, esM)

            # The state of charge at each time step cannot be smaller than the installed capacity multiplied with the
            # relative minimum state of charge
            self.minSOCwithTSAprecise(pyM, esM)

    ####################################################################################################################
    #        Declare component contributions to basic EnergySystemModel constraints and its objective function         #
    ####################################################################################################################

    def getSharedPotentialContribution(self, pyM, key, loc):
        return super().getSharedPotentialContribution(pyM, key, loc)

    def hasOpVariablesForLocationCommodity(self, esM, loc, commod):
        return super().hasOpVariablesForLocationCommodity(esM, loc, commod)

    def getCommodityBalanceContribution(self, pyM, commod, loc, p, t):
        return  super().getCommodityBalanceContribution(pyM, commod, loc, p, t)

    def getObjectiveFunctionContribution(self, esM, pyM):
        return super().getObjectiveFunctionContribution(esM, pyM)

    ####################################################################################################################
    #                                  Return optimal values of the component class                                    #
    ####################################################################################################################

    def setOptimalValues(self, esM, pyM):
        return super().setOptimalValues(esM, pyM)